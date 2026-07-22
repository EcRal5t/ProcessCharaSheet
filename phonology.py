"""Middle-Chinese correspondence model used by audits and safe S2T.

The module is deliberately independent of Excel and ``Sheet``.  Callers provide
already-normalised dialect readings and retain ownership of source-row metadata.
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from chara_trasnlator import split_jpp


MC_INITIALS = "幫滂並明端透定泥來知徹澄孃精清從心邪莊初崇生俟章昌常書船日見溪羣疑影曉匣云以"
MC_RHYMES = "東冬鍾江支脂之微魚虞模齊祭泰佳皆夬灰咍廢眞臻文欣元魂痕寒刪山仙先蕭宵肴豪歌麻陽唐庚耕清青蒸登尤侯幽侵覃談鹽添咸銜嚴凡"
DESC_RE = re.compile(f"([{MC_INITIALS}])([開合])?([一二三四])?([AB])?([{MC_RHYMES}])([平上去入])")

GROUPS = {
    "幫": set("幫滂並明"), "端": set("端透定泥"), "知": set("知徹澄孃"),
    "來": set("來"), "精": set("精清從心邪"), "莊": set("莊初崇生俟"),
    "章": set("章昌常書船"), "日": set("日"), "見": set("見溪羣疑"),
    "影": set("影云曉匣"), "以": set("以"),
}
INIT_TO_GROUP = {initial: group for group, initials in GROUPS.items() for initial in initials}
VOICING = {
    **{char: "全清" for char in "幫端知精心莊生章書見影曉"},
    **{char: "次清" for char in "滂透徹清初昌溪"},
    **{char: "全濁" for char in "並定澄從邪崇俟常船羣匣"},
    **{char: "次濁" for char in "明泥孃來日疑云以"},
}
SHE = {
    "通": set("東冬鍾"), "江": set("江"), "止": set("支脂之微"),
    "遇": set("魚虞模"), "蟹": set("齊佳皆灰咍祭泰夬廢"),
    "臻": set("眞臻文欣元魂痕"), "山": set("寒刪山先仙"),
    "效": set("蕭宵肴豪"), "果": set("歌"), "假": set("麻"),
    "宕": set("唐陽"), "梗": set("庚耕清青"), "曾": set("登蒸"),
    "流": set("侯尤幽"), "深": set("侵"), "咸": set("覃談鹽添咸銜嚴凡"),
}
RHYME_TO_SHE = {rhyme: she for she, rhymes in SHE.items() for rhyme in rhymes}
OPENNESS_NEUTRAL_RHYMES = set("東冬鍾江虞模尤幽")
INHERENT_OPEN_RHYMES = set("咍痕欣嚴之魚臻蕭宵肴豪侯侵覃談鹽添咸銜")
INHERENT_CLOSED_RHYMES = set("灰魂文凡")
DIVISION_RHYMES = {
    "一": set("冬模泰咍灰痕魂寒豪唐登侯覃談"),
    "二": set("江佳皆夬刪山肴耕咸銜"),
    "三": set("鍾支脂之微魚虞祭廢眞臻欣元文仙宵陽清蒸尤幽侵鹽嚴凡"),
    "四": set("齊先蕭青添"),
}
RHYME_TO_DIVISION = {
    rhyme: division
    for division, rhymes in DIVISION_RHYMES.items()
    for rhyme in rhymes
}


@dataclass(frozen=True)
class MCPosition:
    description: str
    initial: str
    openness: str
    division: str
    chongniu: str
    rhyme: str
    tone: str

    @property
    def group(self) -> str:
        return INIT_TO_GROUP.get(self.initial, "")

    @property
    def voicing(self) -> str:
        return VOICING.get(self.initial, "")

    @property
    def she(self) -> str:
        return RHYME_TO_SHE.get(self.rhyme, "")

    @property
    def effective_openness(self) -> str:
        if self.openness:
            return self.openness
        if self.rhyme in OPENNESS_NEUTRAL_RHYMES:
            return "中"
        if self.rhyme in INHERENT_OPEN_RHYMES:
            return "開"
        if self.rhyme in INHERENT_CLOSED_RHYMES:
            return "合"
        return ""

    @property
    def effective_division(self) -> str:
        return self.division or RHYME_TO_DIVISION.get(self.rhyme, "")


@dataclass(frozen=True)
class Pronunciation:
    raw: str
    initial: str
    final: str
    tone: str


@dataclass(frozen=True)
class Pair:
    char: str
    pronunciation: Pronunciation
    position: MCPosition


@dataclass(frozen=True)
class WeightedPair:
    pair: Pair
    weight: float


@dataclass(frozen=True)
class Thresholds:
    total_p95: float
    components_p95: tuple[float, float, float]
    total_p99: float
    components_p99: tuple[float, float, float]


@dataclass(frozen=True)
class FittedCorrespondence:
    model: "CorrespondenceModel"
    thresholds: Thresholds
    seed_count: int
    augmented_pair_count: int
    augmented_char_count: int
    rounds: tuple[dict[str, object], ...]


Dialect = Mapping[str, set[Pronunciation]]
MiddleChinese = Mapping[str, set[MCPosition]]


class HierarchicalDistribution:
    """Dirichlet back-off distribution from broad to specific contexts."""

    def __init__(self, alpha: float = 6.0, beta: float = 0.5):
        self.alpha = alpha
        self.beta = beta
        self.global_counts: Counter[str] = Counter()
        self.level_counts: list[defaultdict[tuple[str, ...], Counter[str]]] = []

    def fit(self, rows: Iterable[tuple[str, list[tuple[str, ...]], float]]) -> None:
        cached = list(rows)
        level_count = max((len(contexts) for _, contexts, _ in cached), default=0)
        self.level_counts = [defaultdict(Counter) for _ in range(level_count)]
        for outcome, contexts, weight in cached:
            self.global_counts[outcome] += weight
            for index, context in enumerate(contexts):
                self.level_counts[index][context][outcome] += weight

    def probability(self, outcome: str, contexts: list[tuple[str, ...]]) -> float:
        vocabulary = max(len(self.global_counts) + 1, 2)
        total = sum(self.global_counts.values())
        probability = (self.global_counts[outcome] + self.beta) / (total + self.beta * vocabulary)
        for index in reversed(range(min(len(contexts), len(self.level_counts)))):
            counts = self.level_counts[index].get(contexts[index])
            if counts:
                probability = (counts[outcome] + self.alpha * probability) / (sum(counts.values()) + self.alpha)
        return max(probability, 1e-12)

    def global_probability(self, outcome: str) -> float:
        vocabulary = max(len(self.global_counts) + 1, 2)
        total = sum(self.global_counts.values())
        return max((self.global_counts[outcome] + self.beta) / (total + self.beta * vocabulary), 1e-12)

    def ranked(
        self,
        contexts: list[tuple[str, ...]],
        *,
        candidates: Iterable[str] | None = None,
        limit: int = 4,
        relative_floor: float = 0.1,
    ) -> list[tuple[str, float]]:
        outcomes = set(candidates if candidates is not None else self.global_counts)
        ranked = sorted(
            ((outcome, self.probability(outcome, contexts)) for outcome in outcomes),
            key=lambda item: (-item[1], item[0]),
        )
        if not ranked:
            return []
        floor = ranked[0][1] * relative_floor
        return [item for item in ranked if item[1] >= floor][:limit]


class CorrespondenceModel:
    def __init__(
        self,
        pairs: Sequence[Pair],
        component_evidence: Mapping[str, Sequence[Pair]] | None = None,
    ):
        if not pairs:
            raise ValueError("cannot fit a correspondence model without seed pairs")
        evidence = component_evidence or {}
        pair_counts = Counter(pair.char for pair in pairs)

        def observations_for(component: str) -> tuple[WeightedPair, ...]:
            base_keys = {
                (pair.char, pair.pronunciation.raw, pair.position.description)
                for pair in pairs
            }
            extras = []
            extra_keys = set()
            for pair in evidence.get(component, ()):
                key = (pair.char, pair.pronunciation.raw, pair.position.description)
                if key not in base_keys and key not in extra_keys:
                    extras.append(pair)
                    extra_keys.add(key)
            effective_pairs = [*pairs, *extras]
            effective_counts = Counter(pair.char for pair in effective_pairs)
            return tuple(
                WeightedPair(pair, 1.0 / effective_counts[pair.char])
                for pair in effective_pairs
            )

        self.initial = HierarchicalDistribution()
        self.final = HierarchicalDistribution()
        self.tone = HierarchicalDistribution()
        self.syllable = HierarchicalDistribution()
        self.component_observations = {
            component: observations_for(component)
            for component in ("initial", "final", "tone")
        }
        context_functions = {
            "initial": initial_contexts,
            "final": final_contexts,
            "tone": tone_contexts,
        }
        outcome_functions = {
            "initial": lambda pair: pair.pronunciation.initial,
            "final": lambda pair: pair.pronunciation.final,
            "tone": lambda pair: pair.pronunciation.tone,
        }
        distributions = {
            "initial": self.initial,
            "final": self.final,
            "tone": self.tone,
        }
        for component, distribution in distributions.items():
            distribution.fit(
                (
                    outcome_functions[component](observation.pair),
                    context_functions[component](observation.pair.position),
                    observation.weight,
                )
                for observation in self.component_observations[component]
            )
        self.syllable.fit(
            (pair.pronunciation.raw, syllable_contexts(pair.position), 1.0 / pair_counts[pair.char])
            for pair in pairs
        )

    def score_parts(self, pronunciation: Pronunciation, position: MCPosition) -> tuple[float, float, float]:
        return (
            -math.log2(self.initial.probability(pronunciation.initial, initial_contexts(position))),
            -math.log2(self.final.probability(pronunciation.final, final_contexts(position))),
            -math.log2(self.tone.probability(pronunciation.tone, tone_contexts(position))),
        )

    def global_score_parts(self, pronunciation: Pronunciation) -> tuple[float, float, float]:
        return (
            -math.log2(self.initial.global_probability(pronunciation.initial)),
            -math.log2(self.final.global_probability(pronunciation.final)),
            -math.log2(self.tone.global_probability(pronunciation.tone)),
        )

    def score(self, pronunciation: Pronunciation, position: MCPosition) -> float:
        return sum(self.score_parts(pronunciation, position))

    def predict_variants(self, position: MCPosition, limit: int = 4) -> tuple[str, ...]:
        contexts = syllable_contexts(position)
        exact = self.syllable.level_counts[0].get(contexts[0]) if self.syllable.level_counts else None
        candidates = exact.keys() if exact else None
        return tuple(
            outcome
            for outcome, _probability in self.syllable.ranked(
                contexts,
                candidates=candidates,
                limit=limit,
                relative_floor=0.1,
            )
        )


def initial_contexts(position: MCPosition) -> list[tuple[str, ...]]:
    return [
        (
            position.initial, position.rhyme, position.effective_openness,
            position.effective_division, position.chongniu,
        ),
        (position.initial, position.rhyme, position.effective_openness, position.effective_division),
        (position.initial, position.rhyme, position.effective_openness),
        (position.initial, position.rhyme),
        (position.initial, position.she),
        (position.initial,),
        (position.group, position.she),
        (position.group,),
    ]


def final_contexts(position: MCPosition) -> list[tuple[str, ...]]:
    return [
        (
            position.rhyme, position.effective_openness, position.effective_division,
            position.chongniu, position.initial,
        ),
        (
            position.rhyme, position.effective_openness, position.effective_division,
            position.chongniu, position.group,
        ),
        (position.rhyme, position.effective_openness, position.effective_division, position.chongniu),
        (position.rhyme, position.effective_openness, position.effective_division, position.group),
        (position.rhyme, position.effective_openness, position.effective_division),
        (position.rhyme, position.effective_openness, position.group),
        (position.rhyme, position.effective_openness),
        (position.rhyme, position.group),
        (position.rhyme,),
        (position.she, position.group),
        (position.she,),
    ]


def tone_contexts(position: MCPosition) -> list[tuple[str, ...]]:
    return [
        (position.tone, position.voicing, position.group),
        (position.tone, position.voicing),
        (position.tone, position.group),
        (position.tone,),
    ]


def syllable_contexts(position: MCPosition) -> list[tuple[str, ...]]:
    return [
        (position.description,),
        (
            position.initial, position.effective_openness, position.effective_division,
            position.chongniu, position.rhyme, position.tone,
        ),
        (position.group, position.she, position.tone),
    ]


def parse_position(description: str) -> MCPosition | None:
    match = DESC_RE.fullmatch(description)
    if not match:
        return None
    initial, openness, division, chongniu, rhyme, tone = (value or "" for value in match.groups())
    return MCPosition(description, initial, openness, division, chongniu, rhyme, tone)


def parse_pronunciation(text: str) -> Pronunciation | None:
    text = text.strip()
    if not text or text == "_":
        return None
    (initial, nucleus, coda), tone = split_jpp(text, norm=False)
    if not nucleus or not tone or initial + nucleus + coda + tone != text:
        return None
    return Pronunciation(text, initial, nucleus + coda, tone)


def read_middle_chinese(path: Path) -> tuple[dict[str, set[MCPosition]], dict[str, int]]:
    """Read qieyun-auto ``KwangUon.csv`` by column name, with old-index fallback."""
    by_char: defaultdict[str, set[MCPosition]] = defaultdict(set)
    stats = Counter()
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            stats["total_rows"] += 1
            description = row.get("最簡描述", "")
            head = row.get("字頭", "") or row.get("字頭覈校前", "")
            position = parse_position(description)
            if not head or position is None:
                stats["unparsed"] += 1
                continue
            head = unicodedata.normalize("NFC", head)
            if len(head) != 1:
                stats["non_single_char"] += 1
                continue
            by_char[head].add(position)
    stats["unique_chars"] = len(by_char)
    stats["unique_positions"] = sum(map(len, by_char.values()))
    return dict(by_char), dict(stats)


def resolve_strict_aliases(
    dialect: Dialect,
    middle_chinese: MiddleChinese,
    strict_relations: Mapping[str, tuple[str, ...]],
) -> tuple[dict[str, set[MCPosition]], dict[str, str]]:
    """Add only versioned strict S2T targets; no OpenCC or variant guessing."""
    resolved = {char: set(positions) for char, positions in middle_chinese.items()}
    provenance: dict[str, str] = {}
    for char in dialect:
        targets = [char] if char in middle_chinese else []
        targets.extend(target for target in strict_relations.get(char, ()) if target in middle_chinese)
        if not targets:
            continue
        resolved[char] = set().union(*(middle_chinese[target] for target in targets))
        provenance[char] = "+".join(
            "direct" if target == char else f"strict-s2t:{target}" for target in targets
        )
    return resolved, provenance


def make_seed_pairs(
    dialect: Dialect,
    middle_chinese: MiddleChinese,
    *,
    excluded_chars: set[str] | None = None,
) -> list[Pair]:
    excluded = excluded_chars or set()
    result = []
    for char in sorted(dialect):
        if char in excluded:
            continue
        if len(dialect[char]) == 1 and len(middle_chinese.get(char, ())) == 1:
            result.append(Pair(char, next(iter(dialect[char])), next(iter(middle_chinese[char]))))
    return result


def fold_for_char(char: str, folds: int = 5) -> int:
    digest = hashlib.blake2b(char.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big") % folds


def quantile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    index = (len(ordered) - 1) * q
    lower, upper = math.floor(index), math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - index) + ordered[upper] * (index - lower)


def best_location(
    model: CorrespondenceModel,
    pronunciation: Pronunciation,
    positions: Iterable[MCPosition],
) -> tuple[float, MCPosition, float]:
    scored = sorted((model.score(pronunciation, position), position.description, position) for position in positions)
    best_score, _, best_position = scored[0]
    margin = scored[1][0] - best_score if len(scored) > 1 else math.inf
    return best_score, best_position, margin


def cross_validated_thresholds(pairs: Sequence[Pair], folds: int = 5) -> Thresholds:
    totals: list[float] = []
    components: list[list[float]] = [[], [], []]
    for fold in range(folds):
        train = [pair for pair in pairs if fold_for_char(pair.char, folds) != fold]
        test = [pair for pair in pairs if fold_for_char(pair.char, folds) == fold]
        if not train:
            continue
        model = CorrespondenceModel(train)
        for pair in test:
            parts = model.score_parts(pair.pronunciation, pair.position)
            totals.append(sum(parts))
            for index, value in enumerate(parts):
                components[index].append(value)
    if not totals:
        raise ValueError("not enough seed pairs for cross-validation")
    return Thresholds(
        quantile(totals, 0.95),
        tuple(quantile(values, 0.95) for values in components),  # type: ignore[arg-type]
        quantile(totals, 0.99),
        tuple(quantile(values, 0.99) for values in components),  # type: ignore[arg-type]
    )


def discover_systematic_component_evidence(
    dialect: Dialect,
    middle_chinese: MiddleChinese,
    *,
    excluded_chars: set[str] | None = None,
    provisional_model: CorrespondenceModel | None = None,
    minimum_other_char_support: int = 6,
    minimum_reverse_purity: float = 0.7,
    minimum_forward_rate: float = 0.12,
) -> tuple[dict[str, tuple[Pair, ...]], dict[str, object]]:
    """Find recurrent component correspondences without requiring prior acceptance.

    Ordinary evidence uses characters with one Middle-Chinese position, so its
    historical source is unambiguous.  A relation is retained when it occurs
    across several different characters and is either common for that context
    or strongly diagnostic in the reverse direction.  Recurrent co-alternants
    may additionally borrow an understood counterpart's position even on a
    multi-position character.  This lets layers such as Zhanjiang ``心母 -> sl``
    and secondary ``v -> w`` bootstrap themselves.
    """
    excluded = excluded_chars or set()
    contexts_for = {
        "initial": lambda position: [
            (f"@{index}", *initial_contexts(position)[index])
            for index in (0, 3, 4, 5, 6)
        ],
        "final": lambda position: [
            (f"@{index}", *final_contexts(position)[index])
            for index in (0, 1, 2, 7, 8, 9, 10)
        ],
        "tone": lambda position: [
            (f"@{index}", *tone_contexts(position)[index])
            for index in (0, 1, 3)
        ],
    }
    outcome_for = {
        "initial": lambda pronunciation: pronunciation.initial,
        "final": lambda pronunciation: pronunciation.final,
        "tone": lambda pronunciation: pronunciation.tone,
    }
    signature_for = {
        "initial": lambda pronunciation: (pronunciation.final, pronunciation.tone),
        "final": lambda pronunciation: (pronunciation.initial, pronunciation.tone),
        "tone": lambda pronunciation: (pronunciation.initial, pronunciation.final),
    }

    # Recurrent co-alternants provide a route for a secondary layer to borrow
    # the historical assignment of an already understood primary layer.  This
    # is especially important when the secondary outcome never occurs alone.
    alternation_chars: dict[str, defaultdict[tuple[str, str], set[str]]] = {
        name: defaultdict(set) for name in contexts_for
    }
    for char in sorted(set(dialect) - excluded):
        pronunciations = sorted(dialect[char], key=lambda value: value.raw)
        for left, right in itertools.combinations(pronunciations, 2):
            for component in contexts_for:
                if signature_for[component](left) != signature_for[component](right):
                    continue
                outcomes = tuple(sorted((outcome_for[component](left), outcome_for[component](right))))
                if outcomes[0] != outcomes[1]:
                    alternation_chars[component][outcomes].add(char)
    qualified_alternations = {
        component: {
            outcomes for outcomes, chars in alternation_chars[component].items()
            if len(chars) - 1 >= minimum_other_char_support
        }
        for component in contexts_for
    }
    alternation_evidence: dict[str, list[Pair]] = {name: [] for name in contexts_for}
    if provisional_model is not None:
        distributions = {
            "initial": provisional_model.initial,
            "final": provisional_model.final,
            "tone": provisional_model.tone,
        }
        model_contexts = {
            "initial": initial_contexts,
            "final": final_contexts,
            "tone": tone_contexts,
        }
        for char in sorted((set(dialect) & set(middle_chinese)) - excluded):
            positions = sorted(middle_chinese[char], key=lambda value: value.description)
            pronunciations = sorted(dialect[char], key=lambda value: value.raw)
            for left, right in itertools.combinations(pronunciations, 2):
                for component in contexts_for:
                    if signature_for[component](left) != signature_for[component](right):
                        continue
                    outcomes = tuple(sorted((outcome_for[component](left), outcome_for[component](right))))
                    if outcomes not in qualified_alternations[component]:
                        continue
                    distribution = distributions[component]
                    context_function = model_contexts[component]
                    left_score = min(
                        -math.log2(distribution.probability(outcome_for[component](left), context_function(position)))
                        for position in positions
                    )
                    right_score = min(
                        -math.log2(distribution.probability(outcome_for[component](right), context_function(position)))
                        for position in positions
                    )
                    if abs(left_score - right_score) < 0.75:
                        continue
                    target, anchor = (left, right) if left_score > right_score else (right, left)
                    anchor_outcome = outcome_for[component](anchor)
                    position_scores = [
                        (
                            -math.log2(distribution.probability(anchor_outcome, context_function(position))),
                            position,
                        )
                        for position in positions
                    ]
                    best = min(score for score, _position in position_scores)
                    alternation_evidence[component].extend(
                        Pair(char, target, position)
                        for score, position in position_scores
                        if score <= best + 0.75
                    )
    candidates: dict[str, list[Pair]] = {name: [] for name in contexts_for}
    relation_chars: dict[str, defaultdict[tuple[tuple[str, ...], str], set[str]]] = {
        name: defaultdict(set) for name in contexts_for
    }
    context_chars: dict[str, defaultdict[tuple[str, ...], set[str]]] = {
        name: defaultdict(set) for name in contexts_for
    }
    outcome_chars: dict[str, defaultdict[str, set[str]]] = {
        name: defaultdict(set) for name in contexts_for
    }
    for char in sorted((set(dialect) & set(middle_chinese)) - excluded):
        positions = middle_chinese[char]
        if len(positions) != 1:
            continue
        position = next(iter(positions))
        for pronunciation in dialect[char]:
            pair = Pair(char, pronunciation, position)
            for component in contexts_for:
                outcome = outcome_for[component](pronunciation)
                candidates[component].append(pair)
                for context in contexts_for[component](position):
                    relation_chars[component][(context, outcome)].add(char)
                    context_chars[component][context].add(char)
                outcome_chars[component][outcome].add(char)

    result: dict[str, tuple[Pair, ...]] = {}
    relation_counts: dict[str, int] = {}
    evidence_counts: dict[str, int] = {}
    for component in contexts_for:
        qualified = set()
        for (context, outcome), chars in relation_chars[component].items():
            support = len(chars)
            # Leave one character out: every admitted row must be backed by at
            # least this many *other* characters, never by its own observation.
            if support - 1 < minimum_other_char_support:
                continue
            forward_rate = (support - 1) / max(len(context_chars[component][context]) - 1, 1)
            reverse_purity = (support - 1) / max(len(outcome_chars[component][outcome]) - 1, 1)
            if forward_rate >= minimum_forward_rate or reverse_purity >= minimum_reverse_purity:
                qualified.add((context, outcome))
        rows = []
        seen = set()
        alternation_keys = {
            (pair.char, pair.pronunciation.raw, pair.position.description)
            for pair in alternation_evidence[component]
        }
        for pair in [*candidates[component], *alternation_evidence[component]]:
            outcome = outcome_for[component](pair.pronunciation)
            relations = [
                (context, outcome)
                for context in contexts_for[component](pair.position)
            ]
            key = (pair.char, pair.pronunciation.raw, pair.position.description)
            if (
                any(relation in qualified for relation in relations) or key in alternation_keys
            ) and key not in seen:
                rows.append(pair)
                seen.add(key)
        result[component] = tuple(rows)
        relation_counts[component] = len(qualified)
        evidence_counts[component] = len(rows)
    return result, {
        "minimum_other_char_support": minimum_other_char_support,
        "minimum_reverse_purity": minimum_reverse_purity,
        "minimum_forward_rate": minimum_forward_rate,
        "qualified_relations": relation_counts,
        "evidence_pairs": evidence_counts,
        "qualified_alternations": {
            component: len(values)
            for component, values in qualified_alternations.items()
        },
    }


def iterative_augment(
    seeds: Sequence[Pair],
    dialect: Dialect,
    middle_chinese: MiddleChinese,
    threshold: float,
    max_rounds: int = 6,
    excluded_chars: set[str] | None = None,
    component_evidence: Mapping[str, Sequence[Pair]] | None = None,
    location_slack: float = 0.75,
) -> tuple[list[Pair], list[dict[str, object]]]:
    accepted = list(seeds)
    used_chars = {pair.char for pair in accepted}
    excluded = excluded_chars or set()
    rounds: list[dict[str, object]] = []
    for round_number in range(1, max_rounds + 1):
        model = CorrespondenceModel(accepted, component_evidence)
        additions: list[Pair] = []
        kinds = Counter()
        for char in sorted((set(dialect) & set(middle_chinese)) - used_chars - excluded):
            pronunciations = sorted(dialect[char], key=lambda value: value.raw)
            positions = sorted(middle_chinese[char], key=lambda value: value.description)
            if not (1 <= len(pronunciations) <= 6 and 1 <= len(positions) <= 6):
                continue
            chosen: list[Pair] = []
            for pronunciation in pronunciations:
                scored = sorted(
                    (model.score(pronunciation, position), position.description, position)
                    for position in positions
                )
                best_score = scored[0][0]
                plausible = [
                    position for score, _description, position in scored
                    if score <= threshold and score <= best_score + location_slack
                ]
                if not plausible:
                    chosen = []
                    break
                chosen.extend(Pair(char, pronunciation, position) for position in plausible)
            if chosen:
                chosen = list(dict.fromkeys(chosen))
                additions.extend(chosen)
                used_chars.add(char)
                if len(pronunciations) > 1 and len(positions) > 1:
                    kinds["many_to_many"] += 1
                elif len(pronunciations) > 1:
                    kinds["one_mc_position"] += 1
                elif len(positions) > 1:
                    kinds["one_pronunciation"] += 1
                else:
                    kinds["one_to_one"] += 1
        rounds.append({
            "round": round_number,
            "new_pairs": len(additions),
            "new_chars": len({pair.char for pair in additions}),
            **kinds,
        })
        accepted.extend(additions)
        if not additions:
            break
    return accepted, rounds


def fit_correspondence(
    dialect: Dialect,
    middle_chinese: MiddleChinese,
    *,
    excluded_chars: set[str] | None = None,
) -> FittedCorrespondence:
    seeds = make_seed_pairs(dialect, middle_chinese, excluded_chars=excluded_chars)
    if len(seeds) < 50:
        raise ValueError(f"only {len(seeds)} unambiguous seed pairs; at least 50 are required")
    thresholds = cross_validated_thresholds(seeds)
    component_evidence, evidence_stats = discover_systematic_component_evidence(
        dialect,
        middle_chinese,
        excluded_chars=excluded_chars,
        provisional_model=CorrespondenceModel(seeds),
    )
    augmented, rounds = iterative_augment(
        seeds,
        dialect,
        middle_chinese,
        thresholds.total_p95,
        excluded_chars=excluded_chars,
        component_evidence=component_evidence,
    )
    return FittedCorrespondence(
        CorrespondenceModel(augmented, component_evidence),
        thresholds,
        len(seeds),
        len(augmented),
        len({pair.char for pair in augmented}),
        tuple(({"systematic_component_evidence": evidence_stats}, *rounds)),
    )


def auc(correct: Sequence[float], errors: Sequence[float]) -> float:
    if not correct or not errors:
        return math.nan
    combined = [(value, 0) for value in correct] + [(value, 1) for value in errors]
    combined.sort(key=lambda item: item[0])
    rank_sum = 0.0
    index = 0
    while index < len(combined):
        end = index + 1
        while end < len(combined) and combined[end][0] == combined[index][0]:
            end += 1
        average_rank = (index + 1 + end) / 2
        rank_sum += average_rank * sum(label for _, label in combined[index:end])
        index = end
    error_count, correct_count = len(errors), len(correct)
    return (rank_sum - error_count * (error_count + 1) / 2) / (error_count * correct_count)


def evaluate_synthetic_wrong_rows(
    seeds: Sequence[Pair],
    rows: Mapping[tuple[str, str], list[int]],
    folds: int = 5,
) -> dict[str, object]:
    """Five-fold test using the closest held-out Excel row as a wrong-row donor."""
    correct_scores: list[float] = []
    error_scores: list[float] = []
    model_parts: list[tuple[float, float, float]] = []
    global_parts: list[tuple[float, float, float]] = []
    recovery: list[bool] = []
    for fold in range(folds):
        train = [pair for pair in seeds if fold_for_char(pair.char, folds) != fold]
        test = sorted(
            (pair for pair in seeds if fold_for_char(pair.char, folds) == fold),
            key=lambda pair: min(rows.get((pair.char, pair.pronunciation.raw), [10**9])),
        )
        model = CorrespondenceModel(train)
        for pair in test:
            correct_scores.append(model.score(pair.pronunciation, pair.position))
            model_parts.append(model.score_parts(pair.pronunciation, pair.position))
            global_parts.append(model.global_score_parts(pair.pronunciation))
        for index, pair in enumerate(test):
            donor = None
            for distance in range(1, len(test)):
                for candidate_index in (index - distance, index + distance):
                    if 0 <= candidate_index < len(test) and test[candidate_index].pronunciation.raw != pair.pronunciation.raw:
                        donor = test[candidate_index]
                        break
                if donor is not None:
                    break
            if donor is None:
                continue
            corrupted = model.score(donor.pronunciation, pair.position)
            rightful = model.score(donor.pronunciation, donor.position)
            error_scores.append(corrupted)
            recovery.append(rightful < corrupted)
    p95 = quantile(correct_scores, 0.95)
    gains = []
    for index, component in enumerate(("initial", "final", "tone")):
        model_mean = statistics.fmean(parts[index] for parts in model_parts)
        global_mean = statistics.fmean(parts[index] for parts in global_parts)
        gains.append({
            "component": component,
            "model_bits": model_mean,
            "global_bits": global_mean,
            "gain_bits": global_mean - model_mean,
        })
    return {
        "correct_count": len(correct_scores),
        "synthetic_wrong_row_count": len(error_scores),
        "correct_median_bits": quantile(correct_scores, 0.5),
        "correct_p95_bits": p95,
        "error_median_bits": quantile(error_scores, 0.5),
        "auc": auc(correct_scores, error_scores),
        "error_recall_at_5pct_fpr": sum(score > p95 for score in error_scores) / len(error_scores),
        "right_head_beats_wrong_head": sum(recovery) / len(recovery),
        "component_information_gain": gains,
    }
