"""只适配 RDKit 标准化 API；所有会改变计算视图的操作显式记录。"""

from 核心系统.分子标准化 import StandardizedMolecule, StandardizationStep


class RDKitMoleculeStandardizer:
    def standardize(self, requests):
        from rdkit import Chem, rdBase
        from rdkit.Chem.MolStandardize import rdMolStandardize

        requests = tuple(requests)
        if len({r.compound_id for r in requests}) != len(requests):
            raise ValueError("标准化请求身份不得重复")
        output = []
        for r in requests:
            steps, warnings = [], []
            canonical = parent = tautomer = selected = charge = None
            fragments = ()
            status, reason = "available", None
            parsed = False
            try:
                mol = Chem.MolFromSmiles(r.observed_structure, sanitize=False)
                if mol is None or not mol.GetNumAtoms():
                    raise ValueError("SMILES 缺失或无效")
                Chem.SanitizeMol(mol)
                parsed = True
                canonical = Chem.MolToSmiles(mol, isomericSmiles=True)
                steps.append(StandardizationStep("Chem.SanitizeMol", r.observed_structure, canonical))
                steps.append(StandardizationStep("Chem.MolToSmiles(canonical=True)", canonical, canonical))
                fragments = tuple(Chem.MolToSmiles(x, isomericSmiles=True) for x in Chem.GetMolFrags(mol, asMols=True))
                steps.append(StandardizationStep("Chem.GetMolFrags (report only)", canonical, canonical))
                if r.normalize_charge:
                    for method, operation in (("rdMolStandardize.Cleanup", rdMolStandardize.Cleanup),
                            ("rdMolStandardize.Uncharger.uncharge", rdMolStandardize.Uncharger().uncharge)):
                        before = canonical
                        mol = operation(mol)
                        canonical = Chem.MolToSmiles(mol, isomericSmiles=True)
                        steps.append(StandardizationStep(method, before, canonical))
                    warnings.append("电荷规范化不代表指定 pH 的真实离子化状态")
                if r.extract_parent or r.calculation_view == "parent":
                    parent_mol = rdMolStandardize.FragmentParent(mol, skipStandardize=True)
                    parent = Chem.MolToSmiles(parent_mol, isomericSmiles=True)
                    steps.append(StandardizationStep("rdMolStandardize.FragmentParent(skipStandardize=True)", canonical, parent))
                    warnings.append("parent 为派生结构，未改变原始盐/片段身份")
                if r.canonicalize_tautomer or r.calculation_view == "canonical_tautomer":
                    tautomer = Chem.MolToSmiles(rdMolStandardize.TautomerEnumerator().Canonicalize(mol), isomericSmiles=True)
                    steps.append(StandardizationStep("rdMolStandardize.TautomerEnumerator.Canonicalize", canonical, tautomer))
                    warnings.append("canonical tautomer 不是物种丰度预测")
                selected = {"observed": r.observed_structure, "canonical": canonical,
                            "parent": parent, "canonical_tautomer": tautomer}[r.calculation_view]
                charge = Chem.GetFormalCharge(Chem.MolFromSmiles(selected))
            except Exception as error:
                status = "calculation_failed" if parsed else "invalid_structure"
                reason, selected = f"{type(error).__name__}: {error}", None
            output.append(StandardizedMolecule(r.compound_id, r.observed_structure, r.observed_format,
                canonical, parent, tautomer, fragments, charge, tuple(steps), "RDKit", rdBase.rdkitVersion,
                status, r.calculation_view, selected, tuple(warnings), reason))
        return tuple(output)
