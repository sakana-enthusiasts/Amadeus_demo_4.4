"""复用现有 RDKit 实现和可选 Mordred Python API，不安装依赖、不生成构象。"""

from importlib import import_module, metadata

from 核心系统.分子属性.描述符契约 import CandidateDescriptorSet, DescriptorDefinition, DescriptorValue


class RDKitDescriptorCalculator:
    def catalog(self):
        from .RDKit分子属性计算器 import RDKit分子属性计算器
        return tuple(DescriptorDefinition(x["descriptor_name"], x["engine"], x["engine_version"], x["method"])
                     for x in RDKit分子属性计算器().descriptor_catalog())

    def calculate(self, candidates, request):
        if request.engine != "RDKit":
            raise ValueError("描述符请求 engine 与实现不一致")
        from .RDKit分子属性计算器 import RDKit分子属性计算器
        result = RDKit分子属性计算器().calculate(candidates, (), extended_descriptors=request.descriptor_ids)
        return tuple(CandidateDescriptorSet(x.compound_id, x.structure,
            tuple(DescriptorValue(r.descriptor_name, r.value, r.status, r.unit, r.engine,
                r.engine_version, r.method, "2D", r.canonical_structure, r.reason) for r in x.extended_report)) for x in result)


class MordredDescriptorCalculator:
    @staticmethod
    def _load():
        version = metadata.version("mordredcommunity")
        return import_module("mordred"), version

    def catalog(self):
        backend, version = self._load()
        return tuple(DescriptorDefinition(str(d), "Mordred-community", version, type(d).__module__ + "." + type(d).__name__)
                     for d in backend.Calculator(backend.descriptors, ignore_3D=True).descriptors)

    def calculate(self, candidates, request):
        if request.engine != "Mordred-community":
            raise ValueError("描述符请求 engine 与实现不一致")
        candidates = tuple(candidates)
        if len({c.compound_id for c in candidates}) != len(candidates):
            raise ValueError("compound_id 不得重复")
        if not request.descriptor_ids:
            return tuple(CandidateDescriptorSet(c.compound_id, c.structure, ()) for c in candidates)
        version, unavailable = "unavailable", None
        try:
            backend, version = self._load()
            catalog = {str(d): d for d in backend.Calculator(backend.descriptors, ignore_3D=True).descriptors}
            selected = [catalog[n] for n in request.descriptor_ids if n in catalog]
            calculator = backend.Calculator(selected, ignore_3D=True)
        except (ImportError, metadata.PackageNotFoundError, OSError) as error:
            unavailable = f"{type(error).__name__}: Mordred-community 不可用，请在可选化学环境安装"
        from rdkit import Chem
        output = []
        for candidate in candidates:
            mol = None if unavailable else Chem.MolFromSmiles(candidate.structure)
            if mol is not None and not mol.GetNumAtoms():
                mol = None
            canonical = Chem.MolToSmiles(mol, isomericSmiles=True) if mol is not None else None
            error = None
            try:
                raw = dict(zip((str(d) for d in selected), calculator(mol))) if mol is not None else {}
            except Exception as exc:
                raw, error = {}, f"{type(exc).__name__}: calculation failed"
            values = []
            for name in request.descriptor_ids:
                common = dict(descriptor_id=name, unit=None, engine="Mordred-community", engine_version=version,
                              method=f"mordred:{name}", dimension="2D", canonical_structure=canonical)
                if unavailable:
                    value = DescriptorValue(**common, value=None, status="capability_unavailable", reason=unavailable)
                elif name not in catalog:
                    value = DescriptorValue(**common, value=None, status="unsupported", reason="未注册为 2D 描述符")
                elif mol is None:
                    value = DescriptorValue(**common, value=None, status="invalid_structure", reason="SMILES 缺失或无效")
                else:
                    try:
                        if error:
                            raise ValueError(error)
                        if isinstance(raw[name], bool):
                            raise ValueError("布尔值不是数值描述符")
                        value = DescriptorValue(**common, value=float(raw[name]), status="available")
                    except (TypeError, ValueError, OverflowError, KeyError) as exc:
                        value = DescriptorValue(**common, value=None, status="calculation_failed", reason=f"{type(exc).__name__}: {exc}")
                values.append(value)
            output.append(CandidateDescriptorSet(candidate.compound_id, candidate.structure, tuple(values)))
        return tuple(output)
