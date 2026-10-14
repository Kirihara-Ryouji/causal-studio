"""Auditable wrappers around causal-learn PC and Tigramite PCMCI."""
from __future__ import annotations

import hashlib
import importlib.metadata
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

MAX_ROWS = 100_000
MAX_VARIABLES = 30


@dataclass
class Settings:
    mode: str = "observational"
    algorithm: str = "pc"
    test: str = "fisherz"
    alpha: float = 0.01
    max_lag: int = 3
    missing: str = "reject"
    time_column: str | None = None
    row_order_confirmed: bool = False
    coefficient_threshold: float = 0.1
    temporal_test: str = "parcorr"
    shuffle_samples: int = 199


def read_table(path: str, sheet: str | int = 0) -> pd.DataFrame:
    source = Path(path)
    if source.stat().st_size > 512 * 1024 * 1024:
        raise ValueError("支持不超过 512 MB 的文件，请先拆分数据。")
    if source.suffix.lower() == ".dta":
        with pd.read_stata(source, iterator=True, convert_categoricals=False,
                           convert_missing=False) as reader:
            frame = reader.read(nrows=MAX_ROWS + 1)
            metadata = {"variable_labels": reader.variable_labels(),
                        "value_labels": {name: {str(k): v for k, v in labels.items()}
                                         for name, labels in reader.value_labels().items()}}
        if len(frame) > MAX_ROWS:
            raise ValueError(f"最多支持 {MAX_ROWS:,} 行，请先拆分数据。")
        if frame.empty:
            raise ValueError("Stata 文件没有数据行。")
        for name in frame:
            if pd.api.types.is_string_dtype(frame[name].dtype):
                frame[name] = frame[name].mask(frame[name].eq(""))
        frame.attrs["stata_metadata"] = metadata
        frame.attrs["import_notes"] = ["Stata 导入保留原始变量名和数值编码；值标签仅用于说明，不替换为文本。Stata 缺失值（包括扩展缺失值和空字符串）统一作为缺失值处理。"]
        return frame
    if source.suffix.lower() == ".xlsx":
        raw = pd.read_excel(source, sheet_name=sheet, header=None, nrows=MAX_ROWS + 2)
    elif source.suffix.lower() in (".csv", ".tsv"):
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                raw = pd.read_csv(source, encoding=encoding, sep="\t" if source.suffix.lower() == ".tsv" else ",",
                                  header=None, nrows=MAX_ROWS + 2, low_memory=False)
                break
            except UnicodeDecodeError:
                if encoding == "gb18030":
                    raise ValueError("无法识别文件编码，请另存为 UTF-8 CSV。")
    else:
        raise ValueError("请导入 .csv、.tsv、.xlsx 或 .dta 文件；旧版 .xls 请先另存为 .xlsx。")
    if len(raw) < 2:
        raise ValueError("表格需要首行列名以及至少一行数据。")
    headers = ["" if pd.isna(x) else str(x).strip() for x in raw.iloc[0]]
    if any(not x for x in headers) or len(set(headers)) != len(headers):
        raise ValueError("首行列名必须非空且不能重复。请先修正列名。")
    frame = raw.iloc[1:].reset_index(drop=True)
    frame.columns = headers
    if len(frame) > MAX_ROWS:
        raise ValueError(f"最多支持 {MAX_ROWS:,} 行，请先拆分数据。")
    return frame


def file_hash(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def profile(frame: pd.DataFrame) -> list[dict]:
    rows = []
    for name in frame:
        column = frame[name]
        numeric = pd.to_numeric(column, errors="coerce")
        is_numeric = bool(numeric.notna().sum() == column.notna().sum() and column.notna().any())
        rows.append({"name": name, "type": "数值" if is_numeric else "文本 / 类别",
                     "missing": int(column.isna().sum()), "unique": int(column.nunique()),
                     "eligible": is_numeric and column.nunique() > 1})
    return rows


def _validate_time(frame: pd.DataFrame, cfg: Settings, notes: list[str]) -> pd.DataFrame:
    if not cfg.time_column:
        if not cfg.row_order_confirmed:
            raise ValueError("请选择时间列，或确认每行按等间隔时间顺序排列。")
        notes.append("未提供时间列；等间隔及排序依赖使用者确认，软件未验证。")
        return frame
    if cfg.time_column not in frame:
        raise ValueError("所选时间列不存在。")
    raw = frame[cfg.time_column]
    if raw.isna().any():
        raise ValueError("时间列有缺失值，请先补齐时间索引。")
    values = pd.to_numeric(raw, errors="coerce")
    if values.isna().any():
        dates = pd.to_datetime(raw, errors="coerce", utc=True)
        if dates.isna().any():
            raise ValueError("时间列必须全部为数值或可解析的日期时间。")
        values = pd.Series(dates.array.asi8, index=raw.index)
    if not np.isfinite(values.to_numpy(dtype=float)).all() or values.duplicated().any():
        raise ValueError("时间列含重复或非有限值。首版支持单条时间序列，不支持多人面板数据直接拼接。")
    order = np.argsort(values.to_numpy(), kind="stable")
    sorted_values = values.iloc[order].to_numpy()
    delta = np.diff(sorted_values)
    if not np.allclose(delta, delta[0], rtol=1e-6, atol=0):
        raise ValueError("时间间隔不一致。请先按固定间隔整理数据；软件不会自动插值或压缩缺失时间。")
    if not np.array_equal(order, np.arange(len(frame))):
        notes.append("已按时间列升序排序。")
    notes.append("已验证时间索引唯一且等间隔；滞后单位为一个采样步长。")
    return frame.iloc[order].reset_index(drop=True)


def prepare(frame: pd.DataFrame, columns: list[str], cfg: Settings):
    if cfg.mode not in ("observational", "timeseries"):
        raise ValueError("未知分析模式。")
    allowed = ("pc", "fci", "ges", "lingam", "resit") if cfg.mode == "observational" else ("pcmci", "pcmci_plus", "varlingam", "lpcmci")
    if cfg.algorithm not in allowed:
        raise ValueError("算法与数据模式不匹配。")
    if cfg.test == "gsq" and cfg.algorithm not in ("pc", "fci"):
        raise ValueError("仅 PC / FCI 支持离散 G² 检验。")
    if not 0 <= cfg.coefficient_threshold <= 10:
        raise ValueError("系数阈值必须在 0–10 之间。")
    if cfg.test not in ("fisherz", "gsq") or cfg.missing not in ("reject", "drop"):
        raise ValueError("无效检验或缺失值策略。")
    if cfg.temporal_test not in ("parcorr", "gpdc", "cmiknn") or not 99 <= cfg.shuffle_samples <= 9999:
        raise ValueError("无效时间序列检验；重采样次数应为 99–9999。")
    if cfg.mode == "timeseries" and cfg.algorithm != "varlingam" and cfg.temporal_test != "parcorr":
        if cfg.alpha < 1 / (cfg.shuffle_samples + 1):
            raise ValueError("重采样次数不足以分辨当前 α，请增加次数或提高 α。")
    if not 0 < cfg.alpha < 1 or not 1 <= cfg.max_lag <= 20:
        raise ValueError("显著性阈值须在 0 和 1 之间；最大滞后须为 1–20。")
    if not 2 <= len(columns) <= MAX_VARIABLES or len(set(columns)) != len(columns):
        raise ValueError(f"请选择 2–{MAX_VARIABLES} 个不同的分析变量。")
    if any(c not in frame for c in columns):
        raise ValueError("部分分析变量不存在。")
    if cfg.mode == "timeseries" and cfg.time_column in columns:
        raise ValueError("时间列不能同时作为分析变量，请取消它的勾选。")
    if len(frame) > MAX_ROWS:
        raise ValueError("数据超过 100,000 行上限。")
    if len(frame) < 30:
        raise ValueError("至少需要 30 行数据；此下限不代表样本量充分。")
    notes, encodings = list(frame.attrs.get("import_notes", [])), {}
    if cfg.mode == "timeseries":
        frame = _validate_time(frame, cfg, notes)
    chosen = frame[columns].copy()
    missing_rows = int(chosen.isna().any(axis=1).sum())
    if missing_rows:
        if cfg.mode == "timeseries" or cfg.missing != "drop":
            raise ValueError(f"所选变量有 {missing_rows} 行包含缺失值。" +
                             ("时间序列禁止直接删行，请先处理缺失值。" if cfg.mode == "timeseries" else "请选择完整行分析或先处理缺失值。"))
        chosen = chosen.dropna()
        notes.append(f"完整行分析删除 {missing_rows} 行；若缺失机制并非完全随机，结果可能产生选择偏差。")
    if len(chosen) < max(30, 5 * len(columns)):
        raise ValueError("有效样本过少：至少需要 max(30, 5 × 变量数) 行。")
    if cfg.algorithm == "resit" or (cfg.mode == "timeseries" and cfg.algorithm != "varlingam" and cfg.temporal_test != "parcorr"):
        notes.append("非线性方法按全部选定数据计算，不自动抽样；固定随机种子 2026。大样本的内存与耗时可能很高，运行中可取消。")
    discrete = cfg.mode == "observational" and cfg.test == "gsq"
    if discrete:
        for col in columns:
            if not 2 <= chosen[col].nunique() <= 20:
                raise ValueError(f"离散检验要求每列有 2–20 个类别：{col} 不符合。连续变量请使用 Fisher-Z。")
            codes, levels = pd.factorize(chosen[col], sort=False)
            chosen[col] = codes
            encodings[col] = [str(v) for v in levels]
        notes.append("离散 G² 检验依赖充分的列联表计数；类别多或条件集大时，稀疏计数可能使检验失真。")
        data = chosen.to_numpy(dtype=np.int64)
    else:
        for col in columns:
            numeric = pd.to_numeric(chosen[col], errors="coerce")
            if numeric.isna().any():
                raise ValueError(f"变量「{col}」含非数值内容。连续检验不接受文本类别；普通观测数据可改用离散 G²。")
            chosen[col] = numeric
        data = chosen.to_numpy(dtype=float)
        if not np.isfinite(data).all():
            raise ValueError("数据包含无穷大或非有限值，请先清理。")
        std = data.std(axis=0)
        if np.any(std == 0):
            raise ValueError("所选变量存在常数列，请取消选择。")
        data = (data - data.mean(axis=0)) / std
        if np.linalg.matrix_rank(data) < len(columns):
            raise ValueError("变量存在完全线性依赖（如重复列、总分及全部分量）。请移除冗余变量。")
        if np.linalg.cond(data) > 1e6:
            raise ValueError("变量接近完全共线，数值检验不可靠。请移除冗余变量。")
        low = [col for col in columns if chosen[col].nunique() <= 10]
        if low:
            notes.append("以下数值列取值不超过 10 种，连续检验假设可能不适用：" + "、".join(low))
    if cfg.mode == "timeseries" and len(data) < max(100, 10 * len(columns) * cfg.max_lag):
        raise ValueError("时间序列过短：要求至少 max(100, 10 × 变量数 × 最大滞后) 个采样点。")
    if len(data) < 200:
        notes.append("样本量较小，条件独立检验及方向识别可能不稳定。")
    return data, notes, encodings, missing_rows


def parse_pc_graph(matrix: np.ndarray, columns: list[str], pag=False) -> list[dict]:
    edges = []
    for i in range(len(columns)):
        for j in range(i + 1, len(columns)):
            a, b = int(matrix[i, j]), int(matrix[j, i])
            if a == b == 0:
                continue
            if (a, b) == (-1, 1):
                source, target, kind = columns[i], columns[j], "directed"
            elif (a, b) == (1, -1):
                source, target, kind = columns[j], columns[i], "directed"
            elif (a, b) == (-1, -1):
                source, target, kind = columns[i], columns[j], "undirected"
            elif pag and (a, b) == (1, 1):
                source, target, kind = columns[i], columns[j], "bidirected"
            elif pag and (a, b) == (2, 2):
                source, target, kind = columns[i], columns[j], "circle_circle"
            elif pag and (a, b) in ((2, 1), (1, 2)):
                source, target = (columns[i], columns[j]) if a == 2 else (columns[j], columns[i])
                kind = "circle_arrow"
            elif pag and (a, b) in ((-1, 2), (2, -1)):
                source, target = (columns[i], columns[j]) if a == -1 else (columns[j], columns[i])
                kind = "tail_circle"
            else:
                source, target, kind = columns[i], columns[j], "conflict"
            edges.append(dict(source=source, target=target, kind=kind, lag=0,
                              statistic=None, p_value=None, q_value=None))
    return edges


class _NumpyCompatibleACF:
    """Tigramite 5.2 ACF without NumPy's removed, historically ignored ddof.

    Keep block-length estimation and resampling unchanged. Do not globally
    patch NumPy or disable time-series block shuffling to avoid the error.
    """
    def _get_acf(self, series, max_lag=None):
        if max_lag is None:
            max_lag = int(max(5, .1 * len(series)))
        autocorr = np.ones(max_lag + 1)
        for lag in range(1, max_lag + 1):
            autocorr[lag] = np.corrcoef(series[lag:], series[:-lag])[0, 1]
        return autocorr


def temporal_test(cfg):
    if cfg.temporal_test == "gpdc":
        from tigramite.independence_tests.gpdc import GPDC
        class CompatibleGPDC(_NumpyCompatibleACF, GPDC):
            pass
        return CompatibleGPDC(significance="shuffle_test", sig_samples=cfg.shuffle_samples, seed=2026)
    if cfg.temporal_test == "cmiknn":
        from tigramite.independence_tests.cmiknn import CMIknn
        class CompatibleCMIknn(_NumpyCompatibleACF, CMIknn):
            pass
        return CompatibleCMIknn(significance="shuffle_test", sig_samples=cfg.shuffle_samples, seed=2026, workers=1)
    from tigramite.independence_tests.parcorr import ParCorr
    return ParCorr(significance="analytic")


def parse_temporal_graph(output, columns, max_lag, q_values=None, alpha=.01):
    edges = []
    kinds = {"-->": "directed", "<--": "reverse_directed", "---": "undirected",
             "<->": "bidirected", "o-o": "circle_circle", "o->": "circle_arrow",
             "<-o": "arrow_circle", "--o": "tail_circle", "o--": "circle_tail", "x-x": "conflict"}
    for i, source in enumerate(columns):
        for j, target in enumerate(columns):
            for lag in range(1 if q_values is not None else 0, max_lag + 1):
                mark = str(output["graph"][i, j, lag])
                if lag == 0 and i >= j:
                    continue
                if q_values is not None:
                    if not np.isfinite(q_values[i, j, lag]) or q_values[i, j, lag] > alpha:
                        continue
                    kind = "directed"
                else:
                    if not mark:
                        continue
                    if mark not in kinds:
                        raise ValueError(f"算法返回暂不支持的端点标记 {mark!r}，未生成可能失真的图。")
                    kind = kinds[mark]
                a, b = source, target
                if lag == 0 and kind in ("reverse_directed", "arrow_circle", "circle_tail"):
                    a, b = b, a
                    kind = {"reverse_directed": "directed", "arrow_circle": "circle_arrow", "circle_tail": "tail_circle"}[kind]
                def finite(value):
                    return float(value) if np.isfinite(value) else None
                edges.append(dict(source=a, target=b, kind=kind, lag=lag,
                                  statistic=finite(output["val_matrix"][i, j, lag]),
                                  p_value=finite(output["p_matrix"][i, j, lag]),
                                  q_value=None if q_values is None else finite(q_values[i, j, lag])))
    return edges


def discover(frame: pd.DataFrame, columns: list[str], cfg: Settings,
             source: dict | None = None, progress=None) -> dict:
    start = time.perf_counter()
    progress = progress or (lambda message: None)
    progress("检查数据质量与分析条件…")
    data, notes, encodings, removed = prepare(frame, columns, cfg)
    if cfg.mode == "observational":
        progress("执行 " + cfg.algorithm.upper() + " 结构搜索…")
        if cfg.algorithm == "pc":
            from causallearn.search.ConstraintBased.PC import pc
            graph = pc(data, alpha=cfg.alpha, indep_test=cfg.test, stable=True,
                       uc_rule=0, uc_priority=2, show_progress=False, node_names=columns)
            edges = parse_pc_graph(graph.G.graph, columns)
            algorithm = "PC-stable / " + ("Fisher-Z" if cfg.test == "fisherz" else "G²")
        elif cfg.algorithm == "fci":
            from causallearn.search.ConstraintBased.FCI import fci
            graph, _ = fci(data, independence_test_method=cfg.test, alpha=cfg.alpha,
                           verbose=False, show_progress=False, node_names=columns)
            edges = parse_pc_graph(graph.graph, columns, pag=True)
            algorithm = "FCI / " + ("Fisher-Z" if cfg.test == "fisherz" else "G²")
        elif cfg.algorithm == "ges":
            from causallearn.search.ScoreBased.GES import ges
            graph = ges(data, score_func="local_score_BIC", node_names=columns)
            edges = parse_pc_graph(graph["G"].graph, columns)
            algorithm = "GES / BIC"
            notes.append("使用库默认 BIC 惩罚；GES 不使用显著性 α，也不提供每条边的 p 值。")
        elif cfg.algorithm == "resit":
            from lingam import RESIT
            from sklearn.ensemble import RandomForestRegressor
            model = RESIT(RandomForestRegressor(n_estimators=100, max_depth=4, random_state=2026, n_jobs=1),
                          random_state=2026, alpha=cfg.alpha)
            model.fit(data)
            edges = [dict(source=columns[i], target=columns[j], kind="directed", lag=0,
                          statistic=None, p_value=None, q_value=None)
                     for j in range(len(columns)) for i in range(len(columns))
                     if i != j and model.adjacency_matrix_[j, i] != 0]
            algorithm = "RESIT / 随机森林 + HSIC"
            notes.append("回归器：100 棵随机森林、最大深度 4；α 用于 HSIC 删边。邻接矩阵的 1 仅表示连接，不是效应系数。")
        else:
            from lingam import DirectLiNGAM
            model = DirectLiNGAM(random_state=2026)
            model.fit(data)
            edges = []
            for j, target_name in enumerate(columns):
                for i, source_name in enumerate(columns):
                    coefficient = float(model.adjacency_matrix_[j, i])
                    if i != j and abs(coefficient) > max(cfg.coefficient_threshold, 1e-12):
                        edges.append(dict(source=source_name, target=target_name, kind="directed", lag=0,
                                          statistic=coefficient, p_value=None, q_value=None))
            algorithm = "DirectLiNGAM"
            notes.append(f"显示标准化系数绝对值 > {cfg.coefficient_threshold:g} 的边；阈值不是显著性检验，α 不参与计算。")
        assumptions = ["各行是独立同分布样本；不适用于直接拼接的时间序列或重复测量。",
                       "因果结构无环、满足 Markov 与忠实性假设，且不存在未观测共同原因。",
                       "Fisher-Z 采用线性高斯条件独立检验。" if cfg.test == "fisherz" else "G² 适用于离散变量，条件列联表需要充分样本。",
                       "有向边是算法假设下的方向；无向边代表方向未识别；冲突边需人工复核。",
                       "α 是单次独立性检验阈值，不是边的错误概率；PC / FCI 不作全图 FDR 控制。"]
        if cfg.algorithm == "fci":
            assumptions[1] = "FCI 允许潜在共同原因；依赖无环、Markov 与忠实性假设，输出 PAG 等价类。"
            assumptions[3] = "圆端点表示不确定；双箭头表示潜在混杂结构，并非双向因果；PAG 有向边表达祖先约束，不保证直接效应。"
        elif cfg.algorithm == "ges":
            assumptions[2] = "使用线性高斯 BIC 评分，输出马尔可夫等价类；有向及无向边须分别解读。"
            assumptions[4] = "BIC 分数用于模型搜索，不是因果成立的概率。"
        elif cfg.algorithm == "lingam":
            assumptions[2] = "线性、非高斯且相互独立的外生噪声；高斯数据可能导致错误方向。"
            assumptions[3] = "方向及标准化结构系数依赖 LiNGAM 模型假设；阈值过滤不保证统计显著。"
            assumptions[4] = "本版不提供系数置信区间或 bootstrap 稳定性。"
        elif cfg.algorithm == "resit":
            assumptions[2] = "连续变量、非线性加性噪声模型；噪声相互独立，无潜在共同原因。"
            assumptions[3] = "方向依赖加性噪声模型及回归拟合质量；本版不提供单边 p 值或效应大小。"
            assumptions[4] = "α 用于残差独立性检验，不代表边错误概率；未作全图 FDR 校正。"
    elif cfg.algorithm == "varlingam":
        from lingam import VARLiNGAM
        progress("执行 VARLiNGAM 同期与滞后结构估计…")
        model = VARLiNGAM(lags=cfg.max_lag, criterion=None, random_state=2026)
        model.fit(data)
        edges = []
        for lag, matrix in enumerate(model.adjacency_matrices_):
            for j, target_name in enumerate(columns):
                for i, source_name in enumerate(columns):
                    coefficient = float(matrix[j, i])
                    if (lag or i != j) and abs(coefficient) > max(cfg.coefficient_threshold, 1e-12):
                        edges.append(dict(source=source_name, target=target_name, kind="directed", lag=lag,
                                          statistic=coefficient, p_value=None, q_value=None))
        algorithm = "VARLiNGAM"
        notes.append(f"固定 VAR 阶数 {cfg.max_lag}，不自动选择阶数；显示标准化系数绝对值 > {cfg.coefficient_threshold:g} 的边，α 不参与计算。")
        assumptions = ["单条等间隔、平稳的线性向量自回归序列；滞后阶数应足以涵盖真实依赖。",
                       "同期结构无环；外生噪声非高斯且相互独立，无潜在共同原因。",
                       "允许同期及滞后关系，正滞后表示源变量早于目标变量。",
                       "标准化结构系数不是 p 值；阈值过滤不保证统计显著，本版未提供置信区间。"]
    else:
        from tigramite import data_processing as pp
        from tigramite.pcmci import PCMCI
        progress("执行 " + cfg.algorithm.upper() + " / " + cfg.temporal_test.upper() + " 结构搜索…")
        if cfg.algorithm == "lpcmci":
            from tigramite.lpcmci import LPCMCI
            model_class = LPCMCI
        else:
            model_class = PCMCI
        model = model_class(dataframe=pp.DataFrame(data, var_names=columns),
                            cond_ind_test=temporal_test(cfg), verbosity=0)
        is_plus = cfg.algorithm == "pcmci_plus"
        if cfg.algorithm == "lpcmci":
            output = model.run_lpcmci(tau_min=0, tau_max=cfg.max_lag, pc_alpha=cfg.alpha)
            q_values = None
        elif is_plus:
            output = model.run_pcmciplus(tau_min=0, tau_max=cfg.max_lag, pc_alpha=cfg.alpha,
                                         contemp_collider_rule="majority", conflict_resolution=True,
                                         fdr_method="none")
            q_values = None
        else:
            output = model.run_pcmci(tau_min=1, tau_max=cfg.max_lag,
                                     pc_alpha=cfg.alpha, alpha_level=cfg.alpha, fdr_method="none")
            q_values = model.get_corrected_pvalues(output["p_matrix"], tau_min=1,
                                                  tau_max=cfg.max_lag, fdr_method="fdr_bh")
        edges = parse_temporal_graph(output, columns, cfg.max_lag, q_values, cfg.alpha)
        test_name = {"parcorr": "ParCorr", "gpdc": "GPDC", "cmiknn": "CMIknn"}[cfg.temporal_test]
        algorithm = {"pcmci": "PCMCI", "pcmci_plus": "PCMCI+", "lpcmci": "LPCMCI（实验性）"}[cfg.algorithm] + " / " + test_name
        if q_values is not None:
            algorithm += " / BH-FDR"
        assumptions = ["单条等间隔时间序列，机制平稳；线性关系与适用的残差分布。",
                       "满足因果 Markov 与忠实性假设，不存在未观测共同原因。",
                       "只检验 1 至最大滞后的关系，不识别同期因果边；同期混杂可能影响结果。",
                       "正滞后表示源变量早于目标变量；自回归边表示同一变量过去对现在的依赖。",
                       "q 值是滞后 MCI 检验的 BH 调整值，不是因果为真的概率。",
                       "偏相关统计量用于描述条件关联，不等同于干预效应。"]
        if is_plus:
            assumptions[2] = "同时识别同期与滞后结构；同期方向只在等价类允许的范围内识别。"
            assumptions[4] = "本版 PCMCI+ 不作 FDR 校正；p 值仅描述邻接关系，不检验同期方向。"
        if cfg.algorithm == "lpcmci":
            assumptions[1] = "LPCMCI 允许未观测共同原因；依赖因果 Markov、忠实性及时间展开图无环假设。"
            assumptions[2] = "输出时间序列 PAG：圆端点为不确定，双箭头表示潜在混杂；有向端点表达祖先约束，不保证直接效应。"
            assumptions[4] = "LPCMCI 为实验性方法；未作 FDR 校正，所示 p 值为算法记录的最大检验 p 值，不是方向显著性。"
            assumptions[5] = "所示统计量为 LPCMCI 搜索记录的检验统计量，不是干预效应。"
        if cfg.temporal_test != "parcorr":
            assumptions[0] = "单条等间隔时间序列，机制平稳；非线性检验仍依赖充分样本和有效的条件集。"
            assumptions[5] = ("GPDC 使用高斯过程回归与残差距离相关，依赖加性噪声模型。" if cfg.temporal_test == "gpdc"
                              else "CMIknn 使用近邻条件互信息估计；高维条件集需要更多样本，统计量不表示影响正负。") + "统计量不是干预效应。"
            notes.append(f"使用 {cfg.shuffle_samples} 次重采样检验；随机种子 2026。有限重采样的 p 值分辨率会影响 BH-FDR 后的检出能力。")
            if cfg.temporal_test == "cmiknn":
                notes.append("CMIknn：knn=0.2、秩变换、shuffle_neighbors=5，单工作线程。")
    assumptions.append("观测数据产生候选因果结构；需要结合领域知识、研究设计或干预实验验证。")
    progress("整理关系图与可复核报告…")
    versions = {name: importlib.metadata.version(name) for name in ("numpy", "pandas", "scipy", "causal-learn", "tigramite", "lingam", "scikit-learn", "numba", "dcor")}
    return dict(schema_version=1, created_at=datetime.now(timezone.utc).isoformat(),
                app_version="0.5.0", algorithm=algorithm, settings=asdict(cfg), source=source or {},
                columns=columns, rows_original=len(frame), rows_used=len(data), rows_removed=removed,
                category_encodings=encodings, edges=edges, notes=notes, assumptions=assumptions,
                versions=versions, elapsed_seconds=round(time.perf_counter() - start, 3))


def analysis_worker(queue, frame, columns, cfg, source):
    try:
        result = discover(frame, columns, cfg, source, lambda s: queue.put(("progress", s)))
        queue.put(("result", result))
    except Exception as exc:
        queue.put(("error", str(exc), traceback.format_exc()))


def sample_data(mode: str) -> pd.DataFrame:
    rng = np.random.default_rng(2026)
    if mode == "timeseries":
        n = 1200
        values = np.zeros((n + 200, 3))
        noise = rng.normal(size=values.shape)
        for t in range(2, len(values)):
            values[t, 0] = .65 * values[t - 1, 0] + noise[t, 0]
            values[t, 1] = .7 * values[t - 1, 0] + .35 * values[t - 1, 1] + noise[t, 1]
            values[t, 2] = -.65 * values[t - 2, 1] + noise[t, 2]
        frame = pd.DataFrame(values[200:], columns=["输入信号", "中间响应", "输出响应"])
        frame.insert(0, "时间", pd.date_range("2026-01-01", periods=n, freq="h").astype(str))
        return frame
    n = 2000
    x, y, z, e, w = rng.normal(size=(5, n))
    return pd.DataFrame({"环境条件": x, "设备输入": y, "中间响应": .9*x + .8*y + z,
                         "输出响应": .75*(.9*x + .8*y + z) + e, "独立噪声": w})
