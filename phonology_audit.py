"""Sheet adapter and console renderer for Middle-Chinese audits."""

from __future__ import annotations

import hashlib
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from chara_struct import Sheet
from phonology import (
    FittedCorrespondence,
    MCPosition,
    MiddleChinese,
    Pair,
    Pronunciation,
    best_location,
    evaluate_synthetic_wrong_rows,
    fit_correspondence,
    make_seed_pairs,
    parse_pronunciation,
    read_middle_chinese,
    resolve_strict_aliases,
)


@dataclass(frozen=True)
class DialectData:
    pronunciations: dict[str, set[Pronunciation]]
    rows: dict[tuple[str, str], list[int]]
    meanings: dict[tuple[str, str], list[str]]
    invalid_pronunciations: tuple[dict[str, object], ...]
    unicode_normalizations: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class AuditResult:
    dialect: DialectData
    middle_chinese: dict[str, set[MCPosition]]
    resolved_middle_chinese: dict[str, set[MCPosition]]
    fitted: FittedCorrespondence
    metrics: dict[str, object]
    anomaly_cases: tuple[dict[str, object], ...]


def extract_sheet_readings(sheet: Sheet) -> DialectData:
    pronunciations: defaultdict[str, set[Pronunciation]] = defaultdict(set)
    rows: defaultdict[tuple[str, str], list[int]] = defaultdict(list)
    meanings: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    invalid: list[dict[str, object]] = []
    normalizations: list[dict[str, str]] = []
    for entry in sheet.entry_list:
        if entry.status < 0:
            continue
        raw_char = entry.chara
        char = unicodedata.normalize("NFC", raw_char)
        if char != raw_char:
            normalizations.append({"source": raw_char, "normalized": char})
        for group in entry.multiprons:
            source_rows = sorted(set(group.source_rows or [entry.index + 1]))
            for raw in group.prons:
                pronunciation = parse_pronunciation(raw)
                if pronunciation is None:
                    invalid.append({"char": char, "pronunciation": raw, "rows": source_rows})
                    continue
                pronunciations[char].add(pronunciation)
                key = (char, pronunciation.raw)
                rows[key] = sorted(set(rows[key] + source_rows))
                if group.mean and group.mean not in meanings[key]:
                    meanings[key].append(group.mean)
    return DialectData(
        dict(pronunciations),
        dict(rows),
        dict(meanings),
        tuple(invalid),
        tuple(normalizations),
    )


def _outlier_cases(
    fitted: FittedCorrespondence,
    dialect: DialectData,
    middle_chinese: MiddleChinese,
    *,
    limit: int,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    cases = []
    counts: Counter[str] = Counter()
    for char in sorted(set(dialect.pronunciations) & set(middle_chinese)):
        for pronunciation in dialect.pronunciations[char]:
            positions = middle_chinese[char]
            score, position, _ = best_location(fitted.model, pronunciation, positions)
            all_parts = [fitted.model.score_parts(pronunciation, candidate) for candidate in positions]
            # Overall surprisal must be explained by one coherent MC position;
            # each component, however, is abnormal only if no recorded position
            # of the character can explain that component.
            parts = tuple(min(values[index] for values in all_parts) for index in range(3))
            excesses = (
                score - fitted.thresholds.total_p99,
                *(value - threshold for value, threshold in zip(parts, fitted.thresholds.components_p99)),
            )
            flags = tuple(excess > 0 for excess in excesses)
            if not any(flags):
                continue
            for flag, name in zip(flags, ("overall", "initial", "final", "tone")):
                if flag:
                    counts[name] += 1
            predicted = fitted.model.predict_variants(position)
            cases.append({
                "rows": ",".join(map(str, dialect.rows.get((char, pronunciation.raw), []))),
                "char": char,
                "pronunciation": pronunciation.raw,
                "excess_total": excesses[0],
                "excess_initial": excesses[1],
                "excess_final": excesses[2],
                "excess_tone": excesses[3],
                "predicted": " | ".join(predicted),
                "note": "；".join(dialect.meanings.get((char, pronunciation.raw), ())),
                "max_excess": max(excesses),
            })
    cases.sort(key=lambda row: float(row["max_excess"]), reverse=True)
    return cases[:limit], {name: counts[name] for name in ("overall", "initial", "final", "tone")}


def run_audit(
    sheet: Sheet,
    mc_path: Path,
    strict_relations: Mapping[str, tuple[str, ...]],
    *,
    case_limit: int = 200,
) -> AuditResult:
    dialect = extract_sheet_readings(sheet)
    middle_chinese, mc_stats = read_middle_chinese(mc_path)
    resolved, _provenance = resolve_strict_aliases(
        dialect.pronunciations, middle_chinese, strict_relations
    )
    seeds = make_seed_pairs(dialect.pronunciations, resolved)
    fitted = fit_correspondence(dialect.pronunciations, resolved)
    validation = evaluate_synthetic_wrong_rows(seeds, dialect.rows)
    anomaly_cases, anomaly_counts = _outlier_cases(
        fitted, dialect, resolved, limit=case_limit
    )
    direct_coverage = set(dialect.pronunciations) & set(middle_chinese)
    resolved_coverage = set(dialect.pronunciations) & set(resolved)
    metrics: dict[str, object] = {
        "inputs": {
            "middle_chinese": str(mc_path.resolve()),
            "middle_chinese_sha256": hashlib.sha256(mc_path.read_bytes()).hexdigest(),
        },
        "dialect": {
            "unique_chars": len(dialect.pronunciations),
            "unique_char_pronunciations": sum(map(len, dialect.pronunciations.values())),
            "polyphonic_chars": sum(len(values) > 1 for values in dialect.pronunciations.values()),
            "invalid_pronunciations": len(dialect.invalid_pronunciations),
            "unicode_normalized_heads": len(dialect.unicode_normalizations),
        },
        "middle_chinese": mc_stats,
        "coverage": {
            "direct_chars": len(direct_coverage),
            "resolved_chars": len(resolved_coverage),
            "strict_alias_chars": len(resolved_coverage - direct_coverage),
        },
        "model": {
            "seed_pairs": fitted.seed_count,
            "augmented_pairs": fitted.augmented_pair_count,
            "augmented_chars": fitted.augmented_char_count,
            "total_p95_bits": fitted.thresholds.total_p95,
            "total_p99_bits": fitted.thresholds.total_p99,
            "component_p95_bits": {
                "initial": fitted.thresholds.components_p95[0],
                "final": fitted.thresholds.components_p95[1],
                "tone": fitted.thresholds.components_p95[2],
            },
            "component_p99_bits": {
                "initial": fitted.thresholds.components_p99[0],
                "final": fitted.thresholds.components_p99[1],
                "tone": fitted.thresholds.components_p99[2],
            },
            "rounds": fitted.rounds,
        },
        "validation": validation,
        "anomaly_counts": anomaly_counts,
        "case_limit": case_limit,
    }
    return AuditResult(
        dialect,
        middle_chinese,
        resolved,
        fitted,
        metrics,
        tuple(anomaly_cases),
    )


def render_audit_console(result: AuditResult) -> str:
    lines = [
        "行号\t字头\t读音\t音节信息熵高于正常多少\t声母信息熵高于正常多少\t"
        "韵母信息熵高于正常多少\t声调信息熵高于正常多少\t推测的声母、韵母、声调\t注释"
    ]
    for case in result.anomaly_cases:
        note = str(case["note"]).replace("\n", "\\n").replace("\t", " ")
        lines.append(
            f"{case['rows']}\t{case['char']}\t{case['pronunciation']}\t"
            f"{float(case['excess_total']):+.2f}\t{float(case['excess_initial']):+.2f}\t"
            f"{float(case['excess_final']):+.2f}\t{float(case['excess_tone']):+.2f}\t"
            f"{case['predicted']}\t{note}"
        )
    return "\n".join(lines)
