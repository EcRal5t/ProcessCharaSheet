"""Compact entropy-based Middle-Chinese-to-modern correspondence tables."""

from __future__ import annotations

import hashlib
import html
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from phonology import MC_INITIALS, MC_RHYMES, MCPosition, CorrespondenceModel, Pronunciation


@dataclass(frozen=True)
class TableObservation:
    char: str
    outcome: str
    display_outcome: str
    pronunciation: str
    position: MCPosition
    weight: float


@dataclass
class EntropyNode:
    observations: tuple[TableObservation, ...]
    split_feature: str | None = None
    children: dict[tuple[str, ...], "EntropyNode"] | None = None


@dataclass(frozen=True)
class TableExample:
    char: str
    pronunciations: tuple[str, ...]


@dataclass(frozen=True)
class TableOutcome:
    value: str
    char_count: int
    checked_char_count: int | None
    examples: tuple[TableExample, ...]

    @property
    def total_char_count(self) -> int:
        return self.char_count + (self.checked_char_count or 0)


@dataclass(frozen=True)
class TableRule:
    base: str
    conditions: tuple[tuple[str, str], ...]
    outcomes: tuple[str, ...]
    outcome_details: tuple[TableOutcome, ...]
    entropy_bits: float
    information_gain_bits: float
    char_count: int


FEATURE_LABELS = {
    "openness": "呼",
    "she": "攝",
    "division": "等",
    "chongniu": "重紐",
    "rhyme": "韻",
    "initial": "聲母",
    "group": "組",
    "voicing": "清濁",
    "tone": "調",
}

# Fixed description-length cost in bits.  Broad binary features are cheap;
# naming an exact rhyme/initial must buy substantially more entropy reduction.
FEATURE_COSTS = {
    "openness": 0.0,
    "division": 0.05,
    "chongniu": 0.05,
    "she": 0.20,
    "group": 0.05,
    "voicing": 0.05,
    "rhyme": 1.40,
    "initial": 0.60,
    "tone": 0.05,
}


def _normalise_checked_coda(final: str) -> str:
    """Map checked codas onto their homorganic nasal series for tree fitting."""
    if final.endswith("p"):
        return f"{final[:-1]}m"
    if final.endswith("t"):
        return f"{final[:-1]}n"
    if final.endswith("k"):
        return f"{final[:-1]}ng"
    return final


def _feature(position: MCPosition, name: str) -> str:
    values = {
        "openness": position.effective_openness,
        "she": position.she,
        "division": position.effective_division,
        "chongniu": position.chongniu,
        "rhyme": position.rhyme,
        "initial": position.initial,
        "group": position.group,
        "voicing": position.voicing,
        "tone": position.tone,
    }
    value = values[name] or "無"
    # In a binary 開/合 table, intrinsically neutral rhymes belong to the
    # non-labialised side; their rhyme/she condition can still split below it.
    return "開" if name == "openness" and value == "中" else value


def _weighted_counts(
    observations: Iterable[TableObservation],
    *,
    display: bool = False,
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for observation in observations:
        outcome = observation.display_outcome if display else observation.outcome
        counts[outcome] += observation.weight
    return counts


def _entropy(observations: Sequence[TableObservation]) -> float:
    counts = _weighted_counts(observations)
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    return -sum(
        (count / total) * math.log2(count / total)
        for count in counts.values()
        if count > 0
    )


def _weight(observations: Sequence[TableObservation]) -> float:
    return sum(observation.weight for observation in observations)


def _purity(observations: Sequence[TableObservation]) -> float:
    counts = _weighted_counts(observations)
    total = sum(counts.values())
    return max(counts.values(), default=0.0) / total if total else 0.0


def _modes(
    observations: Sequence[TableObservation],
    limit: int = 4,
    *,
    display: bool = False,
) -> tuple[str, ...]:
    counts = _weighted_counts(observations, display=display)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    if not ranked:
        return ()
    floor = ranked[0][1] * 0.2
    return tuple(outcome for outcome, count in ranked if count >= floor)[:limit]


def _all_outcomes(
    observations: Sequence[TableObservation],
) -> tuple[str, ...]:
    counts = _weighted_counts(observations)
    return tuple(
        outcome
        for outcome, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    )


def _example_limit(char_count: int) -> int:
    """Scale examples gently from one to five as a rule covers more characters."""
    return min(5, max(1, math.ceil(math.sqrt(char_count))))


def _outcome_details(
    observations: Sequence[TableObservation],
    outcomes: Sequence[str],
    *,
    component: str,
) -> tuple[TableOutcome, ...]:
    observations_by_outcome: defaultdict[str, list[TableObservation]] = defaultdict(list)
    for observation in observations:
        observations_by_outcome[observation.outcome].append(observation)
    leaf_has_checked = (
        component == "final"
        and any(
            observation.display_outcome.endswith(("p", "t", "k"))
            for observation in observations
        )
    )

    details = []
    for outcome in outcomes:
        outcome_observations = observations_by_outcome[outcome]
        checked_observations = [
            observation
            for observation in outcome_observations
            if component == "final" and observation.display_outcome.endswith(("p", "t", "k"))
        ]
        regular_observations = [
            observation
            for observation in outcome_observations
            if observation not in checked_observations
        ]
        show_checked_count = leaf_has_checked and outcome.endswith(("m", "n", "ng"))
        regular_chars = {observation.char for observation in regular_observations}
        checked_chars = {observation.char for observation in checked_observations}

        char_weights: Counter[str] = Counter()
        pronunciations_by_char: defaultdict[str, set[str]] = defaultdict(set)
        for observation in outcome_observations:
            char_weights[observation.char] += observation.weight
            pronunciations_by_char[observation.char].add(observation.pronunciation)

        regular_ranked = sorted(
            regular_chars,
            key=lambda char: (-char_weights[char], char),
        )
        checked_ranked = sorted(
            checked_chars,
            key=lambda char: (-char_weights[char], char),
        )
        all_ranked = sorted(char_weights, key=lambda char: (-char_weights[char], char))
        example_limit = _example_limit(len(char_weights))
        if regular_ranked and checked_ranked and example_limit > 1:
            regular_slots = round(
                example_limit * len(regular_chars) / (len(regular_chars) + len(checked_chars))
            )
            regular_slots = min(example_limit - 1, max(1, regular_slots))
            selected_chars = [
                *regular_ranked[:regular_slots],
                *checked_ranked[:example_limit - regular_slots],
            ]
        else:
            selected_chars = all_ranked[:example_limit]
        selected_chars = list(dict.fromkeys(selected_chars))
        for char in all_ranked:
            if len(selected_chars) >= example_limit:
                break
            if char not in selected_chars:
                selected_chars.append(char)

        details.append(TableOutcome(
            outcome,
            len(regular_chars) if show_checked_count else len(char_weights),
            len(checked_chars) if show_checked_count else None,
            tuple(
                TableExample(char, tuple(sorted(pronunciations_by_char[char])))
                for char in selected_chars
            ),
        ))
    return tuple(details)


def _partitions(
    observations: Sequence[TableObservation],
    feature: str,
    minimum_leaf_weight: float,
) -> dict[tuple[str, ...], tuple[TableObservation, ...]]:
    raw: defaultdict[str, list[TableObservation]] = defaultdict(list)
    for observation in observations:
        raw[_feature(observation.position, feature)].append(observation)
    large = {
        (value,): tuple(rows)
        for value, rows in raw.items()
        if _weight(rows) >= minimum_leaf_weight
        or (_weight(rows) >= 2.0 and _purity(rows) >= 0.75)
    }
    small_values = sorted(
        value for value, rows in raw.items()
        if not (
            _weight(rows) >= minimum_leaf_weight
            or (_weight(rows) >= 2.0 and _purity(rows) >= 0.75)
        )
    )
    if small_values:
        small_rows = tuple(
            row
            for value in small_values
            for row in raw[value]
        )
        if _weight(small_rows) >= minimum_leaf_weight:
            large[tuple(small_values)] = small_rows
        elif large:
            small_modes = _modes(small_rows)
            compatible = [
                key for key, rows in large.items()
                if _modes(rows) == small_modes
            ]
            target = compatible[0] if compatible else max(large, key=lambda key: _weight(large[key]))
            rows = large.pop(target)
            large[tuple(sorted((*target, *small_values)))] = (*rows, *small_rows)
    # Fold values that already predict the same meaningful outcome modes before
    # charging the split complexity.  This strongly favours compact conditions.
    folded: defaultdict[tuple[str, ...], list[tuple[tuple[str, ...], tuple[TableObservation, ...]]]] = defaultdict(list)
    for values, rows in large.items():
        folded[_modes(rows)].append((values, rows))
    return {
        tuple(sorted(value for values, _rows in group for value in values)): tuple(
            row for _values, rows in group for row in rows
        )
        for group in folded.values()
    }


def _build_tree(
    observations: Sequence[TableObservation],
    features: Sequence[str],
    *,
    depth: int,
    max_depth: int,
    minimum_leaf_weight: float,
    minimum_gain_bits: float,
    minimum_relative_gain: float,
    complexity_strength: float,
) -> EntropyNode:
    node = EntropyNode(tuple(observations))
    parent_entropy = _entropy(observations)
    total_weight = _weight(observations)
    if depth >= max_depth or parent_entropy < 0.08 or total_weight < minimum_leaf_weight * 2:
        return node

    best: tuple[float, float, str, dict[tuple[str, ...], tuple[TableObservation, ...]]] | None = None
    for feature in features:
        partitions = _partitions(observations, feature, minimum_leaf_weight)
        if len(partitions) < 2:
            continue
        covered = sum(_weight(rows) for rows in partitions.values())
        if covered < total_weight * 0.9:
            continue
        conditional_entropy = sum(
            _weight(rows) / covered * _entropy(rows)
            for rows in partitions.values()
        )
        gain = parent_entropy - conditional_entropy
        penalty = (
            complexity_strength
            * (len(partitions) - 1)
            * math.log2(total_weight + 1)
            / total_weight
        )
        penalized = gain - penalty - FEATURE_COSTS[feature] / (depth + 1)
        candidate = (penalized, gain, feature, partitions)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None:
        return node
    penalized, gain, feature, partitions = best
    if (
        penalized <= 0
        or gain < minimum_gain_bits
        or gain / max(parent_entropy, 1e-12) < minimum_relative_gain
    ):
        return node

    remaining = tuple(value for value in features if value != feature)
    children = {
        values: _build_tree(
            rows,
            remaining,
            depth=depth + 1,
            max_depth=max_depth,
            minimum_leaf_weight=minimum_leaf_weight,
            minimum_gain_bits=minimum_gain_bits,
            minimum_relative_gain=minimum_relative_gain,
            complexity_strength=complexity_strength,
        )
        for values, rows in partitions.items()
    }

    # Merge sibling leaves with the same meaningful modern outcomes.  This is
    # the entropy-tree equivalent of folding irrelevant phonological positions.
    merged: dict[tuple[str, ...], EntropyNode] = {}
    leaf_groups: defaultdict[tuple[str, ...], list[tuple[tuple[str, ...], EntropyNode]]] = defaultdict(list)
    for values, child in children.items():
        if child.split_feature is None:
            leaf_groups[_modes(child.observations)].append((values, child))
        else:
            merged[values] = child
    for group in leaf_groups.values():
        values = tuple(sorted(value for branch, _child in group for value in branch))
        rows = tuple(row for _branch, child in group for row in child.observations)
        merged[values] = EntropyNode(rows)
    if len(merged) < 2:
        return node
    node.split_feature = feature
    node.children = merged
    return node


def _branch_label(values: tuple[str, ...]) -> str:
    if len(values) <= 3:
        return "/".join(values)
    return f"其餘{len(values)}類"


def _rules_from_tree(
    base: str,
    node: EntropyNode,
    component: str,
    conditions: tuple[tuple[str, str], ...] = (),
    base_entropy: float | None = None,
) -> list[TableRule]:
    if base_entropy is None:
        base_entropy = _entropy(node.observations)
    if node.split_feature is None or not node.children:
        entropy = _entropy(node.observations)
        # Keep every attested modern outcome at a leaf.  Rare outcomes remain
        # visible in HTML and are deemphasised there instead of disappearing.
        # For finals, checked codas already use their homorganic nasal outcome;
        # TableOutcome retains separate yang/checked counts.
        outcomes = _all_outcomes(node.observations)
        return [TableRule(
            base,
            conditions,
            outcomes,
            _outcome_details(
                node.observations,
                outcomes,
                component=component,
            ),
            entropy,
            max(base_entropy - entropy, 0.0),
            len({observation.char for observation in node.observations}),
        )]
    rules = []
    label = FEATURE_LABELS[node.split_feature]
    for values, child in sorted(node.children.items(), key=lambda item: item[0]):
        rules.extend(_rules_from_tree(
            base,
            child,
            component,
            (*conditions, (label, _branch_label(values))),
            base_entropy,
        ))
    return rules


def build_correspondence_rules(
    model: CorrespondenceModel,
    component: str,
    *,
    minimum_leaf_weight: float = 6.0,
    minimum_gain_bits: float = 0.15,
    minimum_relative_gain: float = 0.12,
    complexity_strength: float = 0.8,
    max_depth: int = 3,
) -> tuple[TableRule, ...]:
    if component == "initial":
        base_function: Callable[[MCPosition], str] = lambda position: position.initial
        outcome_function = lambda observation: observation.pair.pronunciation.initial
        feature_order = ("tone", "openness", "she", "division", "chongniu", "rhyme")
        base_order = MC_INITIALS
    elif component == "final":
        base_function = lambda position: position.rhyme
        outcome_function = lambda observation: observation.pair.pronunciation.final
        feature_order = ("tone", "group", "voicing", "initial", "openness", "division", "chongniu")
        base_order = MC_RHYMES
    else:
        raise ValueError(f"unsupported correspondence-table component: {component}")

    grouped: defaultdict[str, list[TableObservation]] = defaultdict(list)
    for observation in model.component_observations[component]:
        pair = observation.pair
        display_outcome = outcome_function(observation)
        outcome = (
            _normalise_checked_coda(display_outcome)
            if component == "final"
            else display_outcome
        )
        grouped[base_function(pair.position)].append(TableObservation(
            pair.char,
            outcome,
            display_outcome,
            pair.pronunciation.raw,
            pair.position,
            observation.weight,
        ))
    rules = []
    for base in base_order:
        observations = grouped.get(base)
        if not observations:
            continue
        tree = _build_tree(
            observations,
            feature_order,
            depth=0,
            max_depth=max_depth,
            minimum_leaf_weight=minimum_leaf_weight,
            minimum_gain_bits=minimum_gain_bits,
            minimum_relative_gain=minimum_relative_gain,
            complexity_strength=complexity_strength,
        )
        rules.extend(_rules_from_tree(base, tree, component))
    return tuple(rules)


def render_correspondence_tables(model: CorrespondenceModel) -> str:
    lines = [
        "[聲母歸併]",
        "中古聲母\t附加地位\t現聲母\t條件熵(bits)\t降熵(bits)\t字數",
    ]
    for rule in build_correspondence_rules(model, "initial"):
        conditions = ",".join(f"{name}={value}" for name, value in rule.conditions) or "—"
        lines.append(
            f"{rule.base}\t{conditions}\t{'/'.join(rule.outcomes)}\t"
            f"{rule.entropy_bits:.2f}\t{rule.information_gain_bits:.2f}\t{rule.char_count}"
        )
    lines.extend((
        "[韻母歸併]",
        "中古韻\t附加地位\t現韻母\t條件熵(bits)\t降熵(bits)\t字數",
    ))
    for rule in build_correspondence_rules(model, "final"):
        conditions = ",".join(f"{name}={value}" for name, value in rule.conditions) or "—"
        lines.append(
            f"{rule.base}\t{conditions}\t{'/'.join(rule.outcomes)}\t"
            f"{rule.entropy_bits:.2f}\t{rule.information_gain_bits:.2f}\t{rule.char_count}"
        )
    return "\n".join(lines)


def _colour_for(value: str) -> tuple[str, str, str]:
    """Return deterministic accent, pale background and foreground HSL colours."""
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest()
    hue = int.from_bytes(digest[:2], "big") % 360
    saturation = 50 + digest[2] % 16
    lightness = 84 + digest[3] % 7
    return (
        f"hsl({hue} {saturation}% 42%)",
        f"hsl({hue} {saturation}% {lightness}%)",
        f"hsl({hue} {max(saturation - 12, 35)}% 22%)",
    )


@dataclass(frozen=True)
class HtmlTableRow:
    rule: TableRule
    detail: TableOutcome
    share: float
    prominence: float


def _flatten_html_rows(rules: Sequence[TableRule]) -> list[HtmlTableRow]:
    rows = []
    for rule in rules:
        total = sum(detail.total_char_count for detail in rule.outcome_details)
        for detail in rule.outcome_details:
            share = detail.total_char_count / total if total else 0.0
            prominence = 1.0 if share >= 0.4 else 0.35 + 0.65 * share / 0.4
            rows.append(HtmlTableRow(rule, detail, share, prominence))
    return rows


def _position_parts(row: HtmlTableRow, condition_depth: int) -> tuple[object, ...]:
    conditions: list[object] = list(row.rule.conditions)
    conditions.extend([None] * (condition_depth - len(conditions)))
    return (row.rule.base, *conditions)


def _rowspans(
    rows: Sequence[HtmlTableRow],
    condition_depth: int,
) -> dict[tuple[int, int], int]:
    """Calculate rowspans for each consecutive hierarchical position prefix."""
    parts = [_position_parts(row, condition_depth) for row in rows]
    spans = {}
    for column in range(condition_depth + 1):
        index = 0
        while index < len(parts):
            key = parts[index][:column + 1]
            end = index + 1
            while end < len(parts) and parts[end][:column + 1] == key:
                end += 1
            spans[(index, column)] = end - index
            index = end
    return spans


def _example_note(
    example: TableExample,
    meanings: Mapping[tuple[str, str], Sequence[str]],
    pronunciations: Mapping[str, set[Pronunciation]],
) -> str:
    char_pronunciations = pronunciations.get(example.char, set())
    if (
        len(char_pronunciations) > 1
        and len({
            (pronunciation.initial, pronunciation.final)
            for pronunciation in char_pronunciations
        }) == 1
    ):
        return ""
    notes = []
    for raw in example.pronunciations:
        for note in meanings.get((example.char, raw), ()):
            note = note.strip()
            if note and note not in notes:
                notes.append(note)
    return "；".join(notes)


def _example_html(
    example: TableExample,
    meanings: Mapping[tuple[str, str], Sequence[str]],
    pronunciations: Mapping[str, set[Pronunciation]],
) -> str:
    note = _example_note(example, meanings, pronunciations)
    note_html = (
        f'<span class="example-note">({html.escape(note)})</span>'
        if note else ""
    )
    return (
        '<span class="example">'
        f'<span class="example-char">{html.escape(example.char)}</span>{note_html}'
        "</span>"
    )


def _render_html_rows(
    rules: Sequence[TableRule],
    *,
    condition_depth: int,
    meanings: Mapping[tuple[str, str], Sequence[str]],
    pronunciations: Mapping[str, set[Pronunciation]],
) -> str:
    flat_rows = _flatten_html_rows(rules)
    spans = _rowspans(flat_rows, condition_depth)
    output = []
    for index, row in enumerate(flat_rows):
        rule = row.rule
        detail = row.detail
        modern = detail.value or "∅"
        accent, background, foreground = _colour_for(detail.value)
        examples = "".join(
            _example_html(example, meanings, pronunciations)
            for example in detail.examples
        )
        count = (
            f"{detail.char_count}+{detail.checked_char_count}"
            if detail.checked_char_count is not None
            else str(detail.char_count)
        )
        search_text = " ".join((
            rule.base,
            modern,
            *(f"{name}{value}" for name, value in rule.conditions),
            *(example.char for example in detail.examples),
            *(
                _example_note(example, meanings, pronunciations)
                for example in detail.examples
            ),
        ))
        cells = []
        if (index, 0) in spans:
            rowspan = spans[(index, 0)]
            cells.append(
                f'<th class="base-cell position-cell" scope="rowgroup" rowspan="{rowspan}">'
                f"{html.escape(rule.base)}</th>"
            )
        for depth in range(condition_depth):
            column = depth + 1
            if (index, column) not in spans:
                continue
            rowspan = spans[(index, column)]
            if depth < len(rule.conditions):
                name, value = rule.conditions[depth]
                content = (
                    f'<span class="position-name">{html.escape(name)}</span>'
                    f'<span class="position-value">{html.escape(value)}</span>'
                )
                empty_class = ""
            else:
                content = "&nbsp;"
                empty_class = " position-empty"
            cells.append(
                f'<td class="position-cell{empty_class}" rowspan="{rowspan}">{content}</td>'
            )
        rare_class = " low-frequency" if row.share < 0.4 else ""
        cells.extend((
            f'<td class="modern-cell outcome-cell{rare_class}" '
            f'style="--accent:{accent};--tone-bg:{background};--tone-fg:{foreground};'
            f'--prominence:{row.prominence:.3f}" title="同一地位內佔比 {row.share:.1%}">'
            '<span class="outcome-fade"><span class="tone-dot"></span>'
            f"<strong>{html.escape(modern)}</strong></span></td>",
            f'<td class="count-cell outcome-cell{rare_class}" style="--prominence:{row.prominence:.3f}">'
            f'<span class="outcome-fade">{count}</span></td>',
            f'<td class="examples-cell outcome-cell{rare_class}" style="--prominence:{row.prominence:.3f}">'
            f'<span class="outcome-fade">{examples}</span></td>',
        ))
        output.append(
            f'<tr class="data-row" data-base="{html.escape(rule.base, quote=True)}" '
            f'data-search="{html.escape(search_text, quote=True)}">'
            + "".join(cells)
            + "</tr>"
        )
    return "\n".join(output)


def _render_section(
    *,
    section_id: str,
    title: str,
    subtitle: str,
    base_label: str,
    rules: Sequence[TableRule],
    meanings: Mapping[tuple[str, str], Sequence[str]],
    pronunciations: Mapping[str, set[Pronunciation]],
) -> str:
    row_count = sum(len(rule.outcome_details) for rule in rules)
    base_count = len({rule.base for rule in rules})
    condition_depth = max(
        1,
        max((len(rule.conditions) for rule in rules), default=0),
    )
    condition_headers = "".join(
        f"<th>條件 {index + 1}</th>"
        for index in range(condition_depth)
    )
    return f"""
    <section class="table-card" id="{section_id}">
      <div class="section-heading">
        <div>
          <p class="eyebrow">{base_count} 個中古類 · {row_count} 條對應</p>
          <h2>{html.escape(title)}</h2>
          <p>{html.escape(subtitle)}</p>
        </div>
        <label class="filter">
          <span>篩選</span>
          <input type="search" data-table-filter="{section_id}-table"
                 placeholder="中古音、現音、條件或例字" autocomplete="off">
        </label>
      </div>
      <div class="table-scroll">
        <table id="{section_id}-table">
          <thead>
            <tr>
              <th rowspan="2">{html.escape(base_label)}</th>
              <th colspan="{condition_depth}">附加地位</th>
              <th rowspan="2">現代音</th>
              <th rowspan="2">轄字</th>
              <th rowspan="2">例字</th>
            </tr>
            <tr>
              {condition_headers}
            </tr>
          </thead>
          <tbody>
            {_render_html_rows(
                rules,
                condition_depth=condition_depth,
                meanings=meanings,
                pronunciations=pronunciations,
            )}
          </tbody>
        </table>
        <p class="empty-state" hidden>沒有符合條件的行。</p>
      </div>
    </section>
    """


def render_correspondence_html(
    model: CorrespondenceModel,
    *,
    locale_name: str,
    source_name: str = "",
    meanings: Mapping[tuple[str, str], Sequence[str]] | None = None,
    pronunciations: Mapping[str, set[Pronunciation]] | None = None,
) -> str:
    """Render a self-contained, searchable and print-friendly HTML report."""
    meanings = meanings or {}
    pronunciations = pronunciations or {}
    initial_rules = build_correspondence_rules(model, "initial")
    final_rules = build_correspondence_rules(model, "final")
    source_line = (
        f'<span>來源：{html.escape(source_name)}</span>'
        if source_name else ""
    )
    initial_section = _render_section(
        section_id="initials",
        title="聲母對照",
        subtitle="以中古聲母為主幹，按有足夠解釋力的韻攝、等、開合、重紐或聲調條件展開。",
        base_label="中古聲母",
        rules=initial_rules,
        meanings=meanings,
        pronunciations=pronunciations,
    )
    final_section = _render_section(
        section_id="finals",
        title="韻母對照",
        subtitle="以中古韻為主幹；入聲韻尾按同部位改寫為陽聲韻尾，轄字欄以「陽聲＋入聲」分開計數。",
        base_label="中古韻",
        rules=final_rules,
        meanings=meanings,
        pronunciations=pronunciations,
    )
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(locale_name)} · 中古音與現音對照表</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #18201e;
      --muted: #66716d;
      --line: #dce4e0;
      --paper: #f4f7f5;
      --card: #fff;
      --brand: #0b6655;
      --brand-pale: #dff1eb;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at 12% 0%, #d9eee6 0, transparent 28rem),
        var(--paper);
      color: var(--ink);
      font-family: "Noto Sans CJK TC", "Microsoft JhengHei", "PingFang TC",
                   "Noto Sans CJK SC", system-ui, sans-serif;
      line-height: 1.5;
    }}
    .page {{ width: min(1180px, calc(100% - 32px)); margin: 0 auto; }}
    .hero {{ padding: 64px 0 34px; }}
    .kicker {{
      margin: 0 0 10px; color: var(--brand); font-size: .78rem;
      font-weight: 800; letter-spacing: .16em; text-transform: uppercase;
    }}
    h1 {{ margin: 0; font-size: clamp(2rem, 5vw, 4rem); line-height: 1.08; letter-spacing: -.04em; }}
    .lead {{ max-width: 760px; margin: 18px 0 0; color: var(--muted); font-size: 1.02rem; }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 10px 20px; margin-top: 22px; color: var(--muted); font-size: .88rem; }}
    .meta strong {{ color: var(--ink); }}
    .jump-links {{ display: flex; gap: 10px; margin-top: 26px; }}
    .jump-links a {{
      border: 1px solid var(--line); border-radius: 999px; padding: 8px 14px;
      background: rgba(255,255,255,.72); color: var(--ink); text-decoration: none;
      font-size: .9rem; font-weight: 700;
    }}
    .jump-links a:hover {{ border-color: var(--brand); color: var(--brand); }}
    main {{ display: grid; gap: 28px; padding-bottom: 64px; }}
    .table-card {{
      overflow: hidden; border: 1px solid var(--line); border-radius: 18px;
      background: var(--card); box-shadow: 0 14px 45px rgba(31, 58, 49, .07);
    }}
    .section-heading {{
      display: flex; align-items: end; justify-content: space-between; gap: 24px;
      padding: 20px 22px 15px;
    }}
    .eyebrow {{ margin: 0 0 4px; color: var(--brand); font-size: .76rem; font-weight: 800; letter-spacing: .08em; }}
    h2 {{ margin: 0; font-size: 1.55rem; letter-spacing: -.02em; }}
    .section-heading p:last-child {{ max-width: 720px; margin: 6px 0 0; color: var(--muted); font-size: .88rem; }}
    .filter {{ flex: 0 0 min(300px, 35%); color: var(--muted); font-size: .75rem; font-weight: 700; }}
    .filter span {{ display: block; margin-bottom: 5px; }}
    .filter input {{
      width: 100%; border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px;
      background: #fbfcfb; color: var(--ink); font: inherit; font-size: .88rem; outline: none;
    }}
    .filter input:focus {{ border-color: var(--brand); box-shadow: 0 0 0 3px var(--brand-pale); }}
    .table-scroll {{ overflow-x: auto; border-top: 1px solid var(--line); }}
    table {{ width: 100%; border-collapse: separate; border-spacing: 0; font-size: .84rem; }}
    thead th {{
      position: sticky; top: 0; z-index: 2; padding: 7px 9px; background: #26332f;
      color: #fff; text-align: left; white-space: nowrap; font-size: .7rem; letter-spacing: .04em;
    }}
    tbody th, tbody td {{ padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: middle; }}
    tbody tr:last-child > * {{ border-bottom: 0; }}
    tbody tr:hover > * {{ background-color: #f8faf9; }}
    .position-cell {{
      min-width: 4.6rem; max-width: 8.5rem; border-right: 1px solid var(--line); background: #fbfcfb;
      text-align: center; vertical-align: middle;
    }}
    .base-cell {{
      width: 4.2rem; min-width: 4.2rem; color: #26332f; background: #edf4f0;
      font-size: 1.02rem; font-weight: 800;
    }}
    .position-name {{
      display: inline; margin-right: 3px; color: var(--muted); font-size: .61rem;
      font-weight: 750; letter-spacing: .04em;
    }}
    .position-value {{ display: inline; color: var(--ink); font-weight: 700; }}
    .position-empty {{ min-width: 1.5rem; background: #fff; }}
    .modern-cell {{
      position: relative; min-width: 5.8rem; overflow: hidden; border-left: 4px solid var(--accent);
      background: var(--tone-bg); color: var(--tone-fg); font-size: .92rem; white-space: nowrap;
    }}
    tbody tr:hover .modern-cell {{ background: var(--tone-bg); }}
    .modern-cell::after {{
      position: absolute; z-index: 0; inset: 0; background: #fff;
      opacity: calc(1 - var(--prominence)); content: "";
    }}
    .outcome-fade {{ position: relative; z-index: 1; opacity: var(--prominence); }}
    .tone-dot {{
      display: inline-block; width: 6px; height: 6px; margin-right: 6px;
      border-radius: 50%; background: var(--accent); vertical-align: 1px;
    }}
    .count-cell {{ width: 4.5rem; color: var(--muted); font-variant-numeric: tabular-nums; }}
    .examples-cell {{ min-width: 9rem; }}
    .example {{
      display: inline-flex; align-items: baseline; min-height: 1.5rem; margin: 1px 3px 1px 0;
      border: 1px solid var(--line); border-radius: 5px; padding: 1px 5px; background: #fff;
    }}
    .example-char {{
      font-size: .96rem;
    }}
    .example-note {{ margin-left: 2px; color: var(--muted); font-size: .64rem; }}
    .empty-state {{ margin: 0; padding: 28px; color: var(--muted); text-align: center; }}
    .method {{
      margin: 0 0 56px; border-left: 3px solid #9cb8ae; padding: 2px 0 2px 16px;
      color: var(--muted); font-size: .85rem;
    }}
    .method summary {{ color: var(--ink); cursor: pointer; font-weight: 750; }}
    .method p {{ max-width: 820px; margin: 8px 0 0; }}
    @media (max-width: 720px) {{
      .page {{ width: min(100% - 20px, 1180px); }}
      .hero {{ padding-top: 38px; }}
      .section-heading {{ display: block; padding: 17px 14px 12px; }}
      .filter {{ display: block; margin-top: 18px; }}
      tbody th, tbody td {{ padding: 6px; }}
    }}
    @media print {{
      body {{ background: #fff; }}
      .page {{ width: 100%; }}
      .hero {{ padding: 18px 0; }}
      .jump-links, .filter {{ display: none; }}
      main {{ gap: 16px; }}
      .table-card {{ break-inside: avoid; box-shadow: none; border-radius: 0; }}
      thead th {{ position: static; }}
    }}
  </style>
</head>
<body>
  <header class="hero">
    <div class="page">
      <p class="kicker">Phonological correspondence</p>
      <h1>{html.escape(locale_name)}<br>中古音與現音對照表</h1>
      <p class="lead">同一中古條件若對應多個現代音，已逐音拆行。入聲韻按同部位改寫為陽聲韻，轄字仍分開計數；低於同地位 40% 的少見音會逐步淡化。</p>
      <div class="meta">
        <span>方言點：<strong>{html.escape(locale_name)}</strong></span>
        {source_line}
      </div>
      <nav class="jump-links" aria-label="表格導覽">
        <a href="#initials">聲母對照</a>
        <a href="#finals">韻母對照</a>
      </nav>
    </div>
  </header>
  <main class="page">
    {initial_section}
    {final_section}
  </main>
  <footer class="page">
    <details class="method">
      <summary>讀表與取例說明</summary>
      <p>附加地位只保留能帶來足夠降熵、且足以抵償分支複雜度的條件。韻母轄字若寫成「12+11」，分別表示陽聲字與入聲字。例字按規則內權重排序，每行一至五字；反斜線花括號內是原表備註。若一字的多個音只差聲調，備註省略。</p>
    </details>
  </footer>
  <script>
    document.querySelectorAll("[data-table-filter]").forEach(input => {{
      const table = document.getElementById(input.dataset.tableFilter);
      const empty = table.parentElement.querySelector(".empty-state");
      input.addEventListener("input", () => {{
        const query = input.value.trim().toLocaleLowerCase();
        const rows = Array.from(table.querySelectorAll("tbody tr"));
        const matchingBases = new Set(
          rows
            .filter(row => !query || row.dataset.search.toLocaleLowerCase().includes(query))
            .map(row => row.dataset.base)
        );
        let visible = 0;
        rows.forEach(row => {{
          const match = matchingBases.has(row.dataset.base);
          row.hidden = !match;
          if (match) visible += 1;
        }});
        empty.hidden = visible !== 0;
      }});
    }});
  </script>
</body>
</html>
"""


def write_correspondence_html(
    model: CorrespondenceModel,
    output_path: Path,
    *,
    locale_name: str,
    source_name: str = "",
    meanings: Mapping[tuple[str, str], Sequence[str]] | None = None,
    pronunciations: Mapping[str, set[Pronunciation]] | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_correspondence_html(
            model,
            locale_name=locale_name,
            source_name=source_name,
            meanings=meanings,
            pronunciations=pronunciations,
        ),
        encoding="utf-8",
    )
    return output_path.resolve()
