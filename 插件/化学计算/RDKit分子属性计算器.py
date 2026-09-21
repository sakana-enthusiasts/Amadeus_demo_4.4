"""正式2D属性和旧描述符adapter共用的RDKit实现；不联网、不读写数据。"""

from rdkit import Chem, rdBase
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors

from 核心系统.分子属性 import CORE_METRICS, MolecularPropertyResult, CandidateMolecularProperties
from 核心系统.结构查询 import StructureCandidate


class RDKit分子属性计算器:
    engine = "RDKit"
    engine_version = rdBase.rdkitVersion
    source = "RDKit 2D descriptor calculation"
    CORE_FUNCTIONS = {
        "logp": Crippen.MolLogP, "tpsa": rdMolDescriptors.CalcTPSA,
        "h_bond_donors": Lipinski.NumHDonors, "h_bond_acceptors": Lipinski.NumHAcceptors,
        "rotatable_bonds": Lipinski.NumRotatableBonds, "aromatic_rings": Lipinski.NumAromaticRings,
        "ring_count": Lipinski.RingCount, "heavy_atom_count": Lipinski.HeavyAtomCount,
        "hetero_atom_count": Lipinski.NumHeteroatoms, "fraction_csp3": Lipinski.FractionCSP3,
        "formal_charge": Chem.GetFormalCharge,
    }
    LEGACY_METRICS = {
        "分子量": "rdkit_molecular_weight", "脂水分配指标_MolLogP": "logp",
        "极性表面积_TPSA": "tpsa", "氢键供体数": "h_bond_donors",
        "氢键受体数": "h_bond_acceptors", "芳香环数量": "aromatic_rings",
        "可旋转键数量": "rotatable_bonds",
    }
    LEGACY_NAMES = tuple(LEGACY_METRICS) + ("芳香性", "基础官能团")
    官能团模式 = {
        "羟基": "[OX2H]", "羧酸": "C(=O)[OX2H1]", "胺基": "[NX3;H1,H2]",
        "肼基": "[NX3][NX3]", "卤素": "[F,Cl,Br,I]", "含硼基团": "[B]",
    }
    Fig1c分类SMARTS = {
        "Alcohol": "[OX2H][CX4;!$(C=O)]", "Sugar": "[C;R]([OX2H])[C;R]([OX2H])",
        "Ether": "[OD2]([#6])[#6]", "Carboxyl": "C(=O)[OX2H1]", "Primary amine": "[NX3;H2][#6]",
        "Secondary amine": "[NX3;H1]([#6])[#6]", "Tertiary amine": "[NX3;H0]([#6])([#6])[#6]",
        "Amide": "C(=O)N", "Urea": "N-C(=O)-N", "Nitrile": "C#N", "Aromatic": "a",
        "Phenyl": "c1ccccc1", "Pyridine": "n1ccccc1", "Sulfur": "[S]", "Halogen": "[F,Cl,Br,I]",
    }

    @staticmethod
    def parse_structure(structure):
        """公开插件内工具入口，缺失/无效结构返回None，不做盐或tautomer归并。"""
        if not isinstance(structure, str) or not structure.strip():
            return None
        try:
            mol = Chem.MolFromSmiles(structure)
            return mol if mol is not None and mol.GetNumAtoms() else None
        except Exception:
            return None

    def descriptor_catalog(self):
        # descList是RDKit提供的2D名称/函数列表，不使用私有_descList或3D模块。
        return [{"descriptor_name": name, "engine": self.engine,
                 "engine_version": self.engine_version, "unit": None,
                 "method": f"Descriptors.{name}", "target_profile_metric": False,
                 "scope": "extended_report", "warning": "单位/语义未正式契约审查；不能用作Target Profile指标"}
                for name, _ in Descriptors.descList]

    def _result(self, metric, descriptor, unit, method, mol, function, canonical):
        common = dict(metric_id=metric, descriptor_name=descriptor, unit=unit, method=method,
                      engine=self.engine, engine_version=self.engine_version, source=self.source,
                      canonical_structure=canonical, structure_format="smiles")
        if unit is None and descriptor is not None:
            common["warning"] = "extended report only：单位/语义未正式契约审查"
        if function is None:
            return MolecularPropertyResult(**common, value=None, status="unsupported", reason="未支持该描述符")
        if mol is None:
            return MolecularPropertyResult(**common, value=None, status="invalid_structure", reason="SMILES 缺失或无效")
        try:
            value = function(mol)
            if isinstance(value, bool):
                raise ValueError("描述符不能把布尔值当作数值")
            if metric in CORE_METRICS and CORE_METRICS[metric].data_type == "int":
                if value != int(value):
                    raise ValueError("count/charge结果不是整数")
                value = int(value)
            else:
                value = float(value)
            return MolecularPropertyResult(**common, value=value, status="available")
        except Exception as error:
            return MolecularPropertyResult(**common, value=None, status="calculation_failed",
                                           reason=f"{type(error).__name__}: {error}")

    def calculate_mol(self, mol, requested_metrics):
        """公开RDKit插件API：同一个Mol复用，精度只在旧adapter中round。"""
        canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True) if mol is not None else None
        results = []
        for metric in requested_metrics:
            metadata = CORE_METRICS.get(metric)
            if metadata:
                results.append(self._result(metric, metadata.descriptor_name, metadata.unit, metadata.method,
                                            mol, self.CORE_FUNCTIONS[metric], canonical))
            elif metric == "rdkit_molecular_weight":
                results.append(self._result(metric, "MolWt", "g/mol", "Descriptors.MolWt",
                                            mol, Descriptors.MolWt, canonical))
            else:
                results.append(self._result(metric, None, None, "unsupported", mol, None, canonical))
        return tuple(results)

    def calculate(self, candidates, requested_metrics, *, extended_descriptors=None):
        if isinstance(requested_metrics, str) or isinstance(extended_descriptors, str):
            raise ValueError("指标/描述符请求须为名称序列，不是字符串")
        metrics = tuple(dict.fromkeys(requested_metrics))
        extended = tuple(dict.fromkeys(extended_descriptors or ()))
        if any(not isinstance(x, str) or not x.strip() for x in metrics + extended):
            raise ValueError("请求名称必须为非空字符串")
        candidates = tuple(candidates)
        if any(not isinstance(x, StructureCandidate) for x in candidates):
            raise ValueError("必须复用StructureCandidate显式输入")
        if len({x.compound_id for x in candidates}) != len(candidates):
            raise ValueError("compound_id 不得重复")
        functions = dict(Descriptors.descList) if extended else {}
        output, cache = [], {}
        for candidate in candidates:
            key = (candidate.structure, candidate.structure_format)
            if key not in cache:
                mol = self.parse_structure(candidate.structure) if metrics or extended else None
                properties = self.calculate_mol(mol, metrics)
                canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True) if mol is not None else None
                report = tuple(self._result("rdkit_" + reformat_name(name), name, None,
                               f"Descriptors.{name}", mol, functions.get(name), canonical) for name in extended)
                cache[key] = (properties, report)
            output.append(CandidateMolecularProperties(candidate.compound_id, candidate.structure,
                          candidate.structure_format, *cache[key]))
        return tuple(output)

    def functional_group_labels(self, mol):
        """旧Fig1c标签的公开兼容API，保留SMARTS、版本和非人工确认语义。"""
        return {f"功能基团_{name}": "是" if mol.HasSubstructMatch(Chem.MolFromSmarts(pattern)) else "否"
                for name, pattern in self.Fig1c分类SMARTS.items()} | {
                "功能基团识别规则": "; ".join(f"{name}:{pattern}" for name, pattern in self.Fig1c分类SMARTS.items()),
                "功能基团_RDKit版本": self.engine_version, "功能基团是否人工确认": "否"}

    def metric_catalog(self):
        """已审查核心指标元数据和当前工具版本；不执行属性计算。"""
        return [x.to_dict() | {"engine": self.engine, "engine_version": self.engine_version,
                              "source": self.source} for x in CORE_METRICS.values()]

    def legacy_descriptors(self, mol, *, include_labels=True):
        """名称→{value,status,reason}；旧长表adapter不重复计算公式。"""
        results = {x.metric_id: x for x in self.calculate_mol(mol, self.LEGACY_METRICS.values())}
        output = {}
        for name, metric in self.LEGACY_METRICS.items():
            result = results[metric]
            value = result.value
            if type(value) is float:
                value = round(value, 6)
            output[name] = {"value": value, "status": result.status, "reason": result.reason}
        try:
            groups = []
            for name, pattern in self.官能团模式.items():
                count = len(mol.GetSubstructMatches(Chem.MolFromSmarts(pattern)))
                if count:
                    groups.append(f"{name}:{count}")
            values = {"芳香性": int(any(atom.GetIsAromatic() for atom in mol.GetAtoms())),
                      "基础官能团": "; ".join(groups) if groups else "未识别基础官能团"}
            if include_labels:
                values |= self.functional_group_labels(mol)
            output |= {name: {"value": value, "status": "available", "reason": None} for name, value in values.items()}
        except Exception as error:
            output |= {name: {"value": None, "status": "calculation_failed", "reason": str(error)}
                       for name in ("芳香性", "基础官能团")}
        return output


def reformat_name(name):
    """扩展描述符仅用报告命名空间；保留原始名称，不注册成正式metric。"""
    import re
    if not isinstance(name, str) or not name:
        raise ValueError("descriptor_name 必须为非空字符串")
    return re.sub(r"[^a-z0-9_]", "_", name.lower())
