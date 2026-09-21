# Amadeus 4.4

## 与 4.3 的区别

本版完成竞品化学能力补齐任务的 Gate A–C，是阶段交付：

- 公开证据执行桥：分子量、密度、折射率、黏度可补入独立执行候选视图；默认关闭，支持只读缓存与显式限量联网，不覆盖用户原值，不平均冲突。
- RDKit 分子标准化：保留原始结构，显式选择 canonical、parent 或 canonical tautomer 计算视图，记录片段、电荷、步骤及工具版本。
- 独立扩展 Descriptor Engine：复用 RDKit，新增可选 Mordred-community 2D Python 适配；只计算显式请求，扩展结果仍为 report-only。
- 主流程、11 项正式 RDKit 指标、Target Profile JSON 1.0、配方算法与 Benchmark 最后加载的顺序保持兼容。

下一项是 Gate D（Structure Query v2/FPSim2）。HSP Advanced、OPERA、Dimorphite-DL、ADMET-AI、结构警报及下游光谱/色素契约尚未实现；本版没有色素筛选或光谱模型。Mordred 未在当前主环境安装，仅完成适配及 mock 验证。

## 数据来源与许可

SeeThrough 补充表、结构映射和参考标签仅用于对应演示及对照，程序不覆盖论文原始表；来源、署名与第三方许可说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。公开证据保留各来源、文献、条件、形式及原始响应关系，不覆盖或静默平均冲突。

项目代码未授予开源许可证，详见 [版权声明.md](版权声明.md)。本地用户数据、完整查询缓存、测试/运行结果、数据库和凭据不应公开；明确维护的最小科学输入与参考表单独列入白名单。
