"""Conservative simplified-head handling backed by phonological evidence."""

from __future__ import annotations

import copy
import csv
import math
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Mapping

from chara_struct import Sheet
from phonology import (
    FittedCorrespondence,
    MCPosition,
    MiddleChinese,
    Pronunciation,
    best_location,
    fit_correspondence,
)
from phonology_audit import DialectData


DEFAULT_RELATION_PATH = Path(__file__).resolve().parent / "data" / "s2t_strict.tsv"
EXPECTED_SOURCE_COUNT = 2546
EXPECTED_PAIR_COUNT = 2574


class PronState(StrEnum):
    REVIEW_ANNOTATED = "REVIEW_ANNOTATED"
    REVIEW_NO_TARGET_MC = "REVIEW_NO_TARGET_MC"
    KEEP_TARGET_OUTLIER = "KEEP_TARGET_OUTLIER"
    KEEP_SOURCE_PHONOLOGY = "KEEP_SOURCE_PHONOLOGY"
    REVIEW_AMBIGUOUS_TARGET = "REVIEW_AMBIGUOUS_TARGET"
    REVIEW_TARGET_EXISTS = "REVIEW_TARGET_EXISTS"
    ELIGIBLE = "ELIGIBLE"


class EntryAction(StrEnum):
    NO_CHANGE = "NO_CHANGE"
    REVIEW = "REVIEW"
    ELIGIBLE = "ELIGIBLE"
    REVIEW_TARGET_COLLISION = "REVIEW_TARGET_COLLISION"


@dataclass(frozen=True)
class PronDecision:
    source: str
    pronunciation: str
    rows: tuple[int, ...]
    note: str
    state: PronState
    target: str | None
    reason: str
    strict_targets: tuple[str, ...]
    source_score_bits: float | None
    target_score_bits: float | None
    target_score_parts_bits: tuple[float, float, float] | None
    target_mc_position: str | None
    target_margin_bits: float | None
    source_margin_bits: float | None


@dataclass(frozen=True)
class EntryDecision:
    source: str
    action: EntryAction
    target: str | None
    pronunciations: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class SafeS2TResult:
    fitted: FittedCorrespondence
    pron_decisions: tuple[PronDecision, ...]
    entry_decisions: tuple[EntryDecision, ...]
    metrics: dict[str, object]


def load_strict_relations(path: Path = DEFAULT_RELATION_PATH) -> dict[str, tuple[str, ...]]:
    targets: defaultdict[str, list[str]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file, delimiter="\t"):
            source, target = row["source"].strip(), row["target"].strip()
            if len(source) != 1 or len(target) != 1:
                raise ValueError(f"strict S2T relation must be single-character: {source!r} -> {target!r}")
            if target not in targets[source]:
                targets[source].append(target)
    result = {source: tuple(values) for source, values in targets.items()}
    pair_count = sum(map(len, result.values()))
    if path.resolve() == DEFAULT_RELATION_PATH.resolve() and (
        len(result) != EXPECTED_SOURCE_COUNT or pair_count != EXPECTED_PAIR_COUNT
    ):
        raise ValueError(
            f"bundled strict S2T data failed integrity count: {len(result)}/{pair_count}"
        )
    return result


def _source_score(
    fitted: FittedCorrespondence,
    pronunciation: Pronunciation,
    source: str,
    middle_chinese: MiddleChinese,
) -> float | None:
    if source not in middle_chinese:
        return None
    return best_location(fitted.model, pronunciation, middle_chinese[source])[0]


def _decide_pronunciation(
    *,
    source: str,
    pronunciation: Pronunciation,
    rows: tuple[int, ...],
    note: str,
    fitted: FittedCorrespondence,
    middle_chinese: MiddleChinese,
    strict_targets: tuple[str, ...],
    table_chars: set[str],
    proof_margin_bits: float,
) -> PronDecision:
    common = dict(
        source=source,
        pronunciation=pronunciation.raw,
        rows=rows,
        note=note,
        strict_targets=strict_targets,
    )
    source_score = _source_score(fitted, pronunciation, source, middle_chinese)
    if note.strip():
        return PronDecision(
            **common,
            state=PronState.REVIEW_ANNOTATED,
            target=None,
            reason="该读音有注释，可能说明本字义、借字、训读或其他例外",
            source_score_bits=source_score,
            target_score_bits=None,
            target_score_parts_bits=None,
            target_mc_position=None,
            target_margin_bits=None,
            source_margin_bits=None,
        )
    candidates: list[tuple[float, str, MCPosition, tuple[float, float, float]]] = []
    for target in strict_targets:
        if target not in middle_chinese:
            continue
        score, position, _ = best_location(fitted.model, pronunciation, middle_chinese[target])
        candidates.append((score, target, position, fitted.model.score_parts(pronunciation, position)))
    candidates.sort(key=lambda item: (item[0], item[1], item[2].description))
    if not candidates:
        return PronDecision(
            **common,
            state=PronState.REVIEW_NO_TARGET_MC,
            target=None,
            reason="严格繁体目标没有可评分的中古音地位",
            source_score_bits=source_score,
            target_score_bits=None,
            target_score_parts_bits=None,
            target_mc_position=None,
            target_margin_bits=None,
            source_margin_bits=None,
        )
    score, target, position, parts = candidates[0]
    target_margin = candidates[1][0] - score if len(candidates) > 1 else math.inf
    source_margin = source_score - score if source_score is not None else math.inf
    evidence = dict(
        target=target,
        source_score_bits=source_score,
        target_score_bits=score,
        target_score_parts_bits=parts,
        target_mc_position=position.description,
        target_margin_bits=target_margin,
        source_margin_bits=source_margin,
    )
    if score > fitted.thresholds.total_p95 or any(
        value > threshold
        for value, threshold in zip(parts, fitted.thresholds.components_p95)
    ):
        return PronDecision(
            **common,
            **evidence,
            state=PronState.KEEP_TARGET_OUTLIER,
            reason="目标繁体的总分或声、韵、调分项超过留出集 P95",
        )
    if target_margin < proof_margin_bits:
        return PronDecision(
            **common,
            **evidence,
            state=PronState.REVIEW_AMBIGUOUS_TARGET,
            reason="多个严格繁体目标的音韵分数过近",
        )
    if source_margin < proof_margin_bits:
        return PronDecision(
            **common,
            **evidence,
            state=PronState.KEEP_SOURCE_PHONOLOGY,
            reason="目标繁体没有显著胜过原字的中古音地位",
        )
    if unicodedata.normalize("NFC", target) in table_chars:
        return PronDecision(
            **common,
            **evidence,
            state=PronState.REVIEW_TARGET_EXISTS,
            reason="目标繁体已经出现在字表中，禁止自动合并或复制",
        )
    return PronDecision(
        **common,
        **evidence,
        state=PronState.ELIGIBLE,
        reason="严格关系、音韵总分及分项、无注释、目标唯一且无碰撞均通过",
    )


def analyze_safe_s2t(
    dialect: DialectData,
    middle_chinese: MiddleChinese,
    strict_relations: Mapping[str, tuple[str, ...]],
    *,
    proof_margin_bits: float = 3.0,
) -> SafeS2TResult:
    fitted = fit_correspondence(
        dialect.pronunciations,
        middle_chinese,
        excluded_chars=set(strict_relations),
    )
    table_chars = {unicodedata.normalize("NFC", char) for char in dialect.pronunciations}
    invalid_chars = {
        str(item["char"])
        for item in dialect.invalid_pronunciations
    }
    pron_decisions: list[PronDecision] = []
    entry_decisions: list[EntryDecision] = []
    for source in sorted(set(dialect.pronunciations) & set(strict_relations)):
        decisions = []
        for pronunciation in sorted(dialect.pronunciations[source], key=lambda item: item.raw):
            key = (source, pronunciation.raw)
            decision = _decide_pronunciation(
                source=source,
                pronunciation=pronunciation,
                rows=tuple(dialect.rows.get(key, ())),
                note="；".join(dialect.meanings.get(key, ())),
                fitted=fitted,
                middle_chinese=middle_chinese,
                strict_targets=strict_relations[source],
                table_chars=table_chars,
                proof_margin_bits=proof_margin_bits,
            )
            decisions.append(decision)
            pron_decisions.append(decision)
        targets = {decision.target for decision in decisions if decision.state == PronState.ELIGIBLE}
        all_eligible = bool(decisions) and all(decision.state == PronState.ELIGIBLE for decision in decisions)
        if source in invalid_chars:
            entry = EntryDecision(
                source, EntryAction.REVIEW, None,
                tuple(decision.pronunciation for decision in decisions),
                "该 Entry 还含无法解析的读音",
            )
        elif all_eligible and len(targets) == 1:
            entry = EntryDecision(
                source, EntryAction.ELIGIBLE, next(iter(targets)),
                tuple(decision.pronunciation for decision in decisions),
                "整个 Entry 的全部读音均指向同一繁体目标",
            )
        elif any(decision.state.name.startswith("REVIEW_") for decision in decisions):
            entry = EntryDecision(
                source, EntryAction.REVIEW, None,
                tuple(decision.pronunciation for decision in decisions),
                "至少一个读音需要人工复核",
            )
        else:
            entry = EntryDecision(
                source, EntryAction.NO_CHANGE, None,
                tuple(decision.pronunciation for decision in decisions),
                "没有满足全部自动条件的完整 Entry",
            )
        entry_decisions.append(entry)

    target_sources: defaultdict[str, list[str]] = defaultdict(list)
    for decision in entry_decisions:
        if decision.action == EntryAction.ELIGIBLE and decision.target:
            target_sources[decision.target].append(decision.source)
    colliding_sources = {
        source
        for sources in target_sources.values() if len(sources) > 1
        for source in sources
    }
    if colliding_sources:
        entry_decisions = [
            EntryDecision(
                decision.source,
                EntryAction.REVIEW_TARGET_COLLISION,
                decision.target,
                decision.pronunciations,
                "多个源字将生成同一个目标 Entry",
            )
            if decision.source in colliding_sources else decision
            for decision in entry_decisions
        ]

    state_counts = Counter(decision.state.value for decision in pron_decisions)
    action_counts = Counter(decision.action.value for decision in entry_decisions)
    metrics: dict[str, object] = {
        "strict_relation_sources": len(strict_relations),
        "strict_relation_pairs": sum(map(len, strict_relations.values())),
        "candidate_entries": len(entry_decisions),
        "candidate_pronunciations": len(pron_decisions),
        "training_seed_pairs_excluding_simplified_sources": fitted.seed_count,
        "training_augmented_pairs": fitted.augmented_pair_count,
        "total_p95_bits": fitted.thresholds.total_p95,
        "component_p95_bits": {
            "initial": fitted.thresholds.components_p95[0],
            "final": fitted.thresholds.components_p95[1],
            "tone": fitted.thresholds.components_p95[2],
        },
        "pronunciation_states": dict(state_counts),
        "entry_actions": dict(action_counts),
        "eligible_entries": [
            {"source": decision.source, "target": decision.target, "pronunciations": decision.pronunciations}
            for decision in entry_decisions
            if decision.action == EntryAction.ELIGIBLE
        ],
    }
    return SafeS2TResult(fitted, tuple(pron_decisions), tuple(entry_decisions), metrics)


def apply_safe_s2t(sheet: Sheet, result: SafeS2TResult, mode: str) -> list[dict[str, str]]:
    if mode not in {"copy", "move"}:
        if mode == "suggest":
            return []
        raise ValueError(f"unknown safe S2T mode: {mode}")
    eligible = {
        decision.source: decision.target
        for decision in result.entry_decisions
        if decision.action == EntryAction.ELIGIBLE and decision.target is not None
    }
    changes = []
    additions = []
    for entry in sheet.entry_list:
        source = unicodedata.normalize("NFC", entry.chara)
        target = eligible.get(source)
        if target is None:
            continue
        if mode == "copy":
            copied = copy.deepcopy(entry)
            copied.chara = target
            copied.status = 1
            additions.append(copied)
        else:
            entry.chara = target
            entry.status = 1
        changes.append({"source": source, "target": target, "mode": mode})
    sheet.entry_list.extend(additions)
    sheet.rebuild_index()
    return changes


def render_safe_s2t_console(result: SafeS2TResult, *, limit: int = 200) -> str:
    metrics = result.metrics
    lines = [
        "",
        "========== 安全简繁审计 ==========" ,
        (
            f"候选 Entry/字音 {metrics['candidate_entries']}/{metrics['candidate_pronunciations']}；"
            f"训练种子/迭代对应 {metrics['training_seed_pairs_excluding_simplified_sources']}/"
            f"{metrics['training_augmented_pairs']}。"
        ),
        f"Pron 状态：{metrics['pronunciation_states']}",
        f"Entry 动作：{metrics['entry_actions']}",
        "",
        "[完整通过的 Entry]",
    ]
    eligible = [
        decision for decision in result.entry_decisions
        if decision.action == EntryAction.ELIGIBLE
    ]
    if eligible:
        lines.append("源字\t目标\t读音")
        for decision in eligible:
            lines.append(
                f"{decision.source}\t{decision.target}\t{'/'.join(decision.pronunciations)}"
            )
    else:
        lines.append("（无）")

    shown = result.pron_decisions[:limit]
    lines.extend(["", f"[逐字音判定] 显示 {len(shown)}/{len(result.pron_decisions)} 条", "Excel行\t字音\t状态\t目标\t总分/声韵调 bits\t理由"])
    for decision in shown:
        if decision.target_score_bits is None or decision.target_score_parts_bits is None:
            scores = "—"
        else:
            scores = (
                f"{decision.target_score_bits:.2f}/"
                + "/".join(f"{value:.2f}" for value in decision.target_score_parts_bits)
            )
        lines.append(
            f"{','.join(map(str, decision.rows))}\t{decision.source} {decision.pronunciation}\t"
            f"{decision.state.value}\t{decision.target or '—'}\t{scores}\t{decision.reason}"
        )
    return "\n".join(lines)
