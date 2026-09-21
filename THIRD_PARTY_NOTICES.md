# 第三方数据与引用说明

## SeeThrough 补充数据

本仓库中的 `数据/论文原始数据/` 包含用于研究演示的 SeeThrough 补充数据表（Supplementary Data 1、2 和 3 的本地工作副本）。来源论文为：

> Liu, Xinyi; Uchigashima, Motokazu; Oomoto, Ikumi; Saito, Yoshihito; Uchida, Hitoshi; Oginezawa, Shinya; Masuda, Keiko; Satoh, Daisuke; Abe, Manabu; Sakimura, Kenji; Shimizu, Yoshihiro; Murayama, Masanori; Tainaka, Kazuki; and Mikuni, Takayasu. *SeeThrough: a rationally designed skull clearing technique for in vivo brain imaging*. Nature Communications 16, 7584 (2025). DOI: [10.1038/s41467-025-62836-1](https://doi.org/10.1038/s41467-025-62836-1).

论文页面将文章主体列为 [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)。文章中另行注明来源的第三方材料不受该许可覆盖；因此本仓库不包含论文 PDF，也不包含论文图像或第三方插图。

为支持可重复的软件演示，本项目对数据的使用方式包括：以补充表作为输入、在运行时做字段名/数据类型标准化、缺失与数值规则处理、候选身份与结构映射，以及派生 RDKit 描述符和 Hansen 距离。`数据/示例数据/` 仅保留复核 10/10 和离线结构处理所需的小型标签/映射表；`数据/导出结果/` 中的 Excel 报告和 PNG 图表是基于上述演示流程生成的派生结果，不是论文插图。上述处理不意味着原论文作者认可本项目或其结论。

请在再分发或改编这些数据时保留适当署名、论文 DOI、CC BY 4.0 说明，并明确说明所做修改。

## 化学计算后端

| 软件/项目 | 代码许可 | 本版用途与依赖方式 | 仓库是否包含第三方源码/模型/数据 |
| --- | --- | --- | --- |
| [RDKit](https://github.com/rdkit/rdkit) | BSD-3-Clause，以上游 LICENSE 为准 | 已有主依赖；4.4 新增 MolStandardize 适配，Descriptor Engine 复用原描述符计算器 | 不 vendor RDKit 源码，不包含其模型/数据 |
| [Mordred-community](https://github.com/JacksonBurns/mordred-community) / [PyPI mordredcommunity](https://pypi.org/project/mordredcommunity/) | BSD-3-Clause | 可选 2.0.7 Python API，显式 2D 扩展描述符；requirements-chemistry.txt，不进入主 requirements | 不包含上游源码、模型或数据；当前环境未安装，adapter/mock 验证 |

Mordred 原始方法论文：Moriwaki H, Tian Y-S, Kawashita N, Takagi T (2018), *Mordred: a molecular descriptor calculator*, Journal of Cheminformatics 10:4，DOI [10.1186/s13321-018-0258-y](https://doi.org/10.1186/s13321-018-0258-y)。使用时同时引用原论文和维护项目。

本轮未集成 HSPiPy、FPSim2、OPERA、Dimorphite-DL 或 ADMET-AI，不将规划工具列作已加入依赖。第三方代码许可不自动覆盖训练数据、模型或公开来源记录，也不改变本项目版权声明。
