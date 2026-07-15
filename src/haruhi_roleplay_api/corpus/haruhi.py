"""凉宫春日小说语料的显式卷册、篇章与时间线映射。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class SectionSpec:
    marker: str
    title: str
    timeline: str
    spoiler_level: int
    branch: str | None = None


@dataclass(frozen=True, kw_only=True)
class BookSpec:
    book_id: str
    volume: int
    filename: str
    title: str
    sections: tuple[SectionSpec, ...]
    stop_markers: tuple[str, ...] = ("後記",)


def _sections(
    markers: tuple[str, ...],
    *,
    timeline: str,
    spoiler_level: int,
) -> tuple[SectionSpec, ...]:
    return tuple(
        SectionSpec(
            marker=marker,
            title=marker,
            timeline=timeline,
            spoiler_level=spoiler_level,
        )
        for marker in markers
    )


def _branched_sections(
    markers: tuple[str, ...],
    *,
    spoiler_level: int = 6,
) -> tuple[SectionSpec, ...]:
    sections: list[SectionSpec] = []
    for marker in markers:
        branch = None
        if marker.startswith("α-"):
            branch = "alpha"
        elif marker.startswith("β-"):
            branch = "beta"
        sections.append(
            SectionSpec(
                marker=marker,
                title=marker,
                timeline="surprise",
                spoiler_level=spoiler_level,
                branch=branch,
            )
        )
    return tuple(sections)


HARUHI_BOOKS: tuple[BookSpec, ...] = (
    BookSpec(
        book_id="v01-melancholy",
        volume=1,
        filename="涼宮春日的憂鬱.txt",
        title="凉宫春日的忧郁",
        sections=_sections(
            ("序曲", "第一章", "第二章", "第三章", "第四章", "第五章", "第六章", "第七章", "尾聲"),
            timeline="melancholy",
            spoiler_level=1,
        ),
    ),
    BookSpec(
        book_id="v02-sigh",
        volume=2,
        filename="涼宮春日的嘆息.txt",
        title="凉宫春日的叹息",
        sections=_sections(
            ("序曲", "第一章", "第二章", "第三章", "第四章", "第五章", "尾聲"),
            timeline="sigh",
            spoiler_level=2,
        ),
    ),
    BookSpec(
        book_id="v03-boredom",
        volume=3,
        filename="涼宮春日的煩悶.txt",
        title="凉宫春日的烦闷",
        sections=_sections(
            ("序曲", "涼宮春日的煩悶", "竹葉狂想曲", "神秘信號", "孤島症候群"),
            timeline="sigh",
            spoiler_level=2,
        ),
    ),
    BookSpec(
        book_id="v04-disappearance",
        volume=4,
        filename="涼宮春日的消失.txt",
        title="凉宫春日的消失",
        sections=_sections(
            ("序曲", "第一章", "第二章", "第三章", "第四章", "第五章", "第六章", "尾聲"),
            timeline="disappearance",
            spoiler_level=4,
        ),
    ),
    BookSpec(
        book_id="v05-rampage",
        volume=5,
        filename="涼宮春日的暴走.txt",
        title="凉宫春日的暴走",
        sections=(
            SectionSpec(
                marker="序章‧夏天",
                title="漫无止境的八月",
                timeline="endless_eight",
                spoiler_level=3,
            ),
            SectionSpec(
                marker="序章‧秋天",
                title="射手座之日",
                timeline="mid_late",
                spoiler_level=5,
            ),
            SectionSpec(
                marker="序章‧冬天",
                title="雪山症候群",
                timeline="mid_late",
                spoiler_level=5,
            ),
        ),
    ),
    BookSpec(
        book_id="v06-wavering",
        volume=6,
        filename="涼宮春日的動搖.txt",
        title="凉宫春日的动摇",
        sections=(
            SectionSpec(marker="Live Alive", title="Live Alive", timeline="sigh", spoiler_level=2),
            SectionSpec(
                marker="朝比奈實玖瑠的冒險Episode00",
                title="朝比奈实玖瑠的冒险 Episode 00",
                timeline="sigh",
                spoiler_level=2,
            ),
            SectionSpec(marker="示愛怪客", title="示爱怪客", timeline="mid_late", spoiler_level=5),
            SectionSpec(marker="尋貓記", title="寻猫记", timeline="mid_late", spoiler_level=5),
            SectionSpec(
                marker="朝比奈實玖瑠的憂鬱",
                title="朝比奈实玖瑠的忧郁",
                timeline="mid_late",
                spoiler_level=5,
            ),
        ),
    ),
    BookSpec(
        book_id="v07-intrigues",
        volume=7,
        filename="涼宮春日的陰謀.txt",
        title="凉宫春日的阴谋",
        sections=_sections(
            ("序曲", "第一章", "第二章", "第三章", "第四章", "第五章", "第六章", "第七章", "尾聲"),
            timeline="mid_late",
            spoiler_level=5,
        ),
    ),
    BookSpec(
        book_id="v08-indignation",
        volume=8,
        filename="涼宮春日的憤慨.txt",
        title="凉宫春日的愤慨",
        sections=_sections(
            ("戴著「總編輯」臂章的惡魔", "犬魔魅影"),
            timeline="mid_late",
            spoiler_level=5,
        ),
    ),
    BookSpec(
        book_id="v09-dissociation",
        volume=9,
        filename="涼宮春日的分裂.txt",
        title="凉宫春日的分裂",
        sections=_branched_sections(
            (
                "序章",
                "第一章",
                "α-1",
                "β-1",
                "β-2",
                "α-2",
                "β-3",
                "α-3",
                "α-4",
                "β-4",
                "第三章",
                "α-5",
                "β-5",
                "α-6",
                "β-6",
            )
        ),
        stop_markers=(),
    ),
    BookSpec(
        book_id="v10-surprise-front",
        volume=10,
        filename="涼宮春日的驚愕〈前〉.txt",
        title="凉宫春日的惊愕（前）",
        sections=_branched_sections(
            ("第四章", "α-7", "β-7", "第五章", "α-8", "β-8", "第六章", "α-9", "β-9")
        ),
        stop_markers=(),
    ),
    BookSpec(
        book_id="v11-surprise-back",
        volume=11,
        filename="涼宮春日的驚愕〈後〉.txt",
        title="凉宫春日的惊愕（后）",
        sections=_branched_sections(
            (
                "第七章",
                "α-10",
                "β-10",
                "第八章",
                "α-11",
                "β-11",
                "第九章",
                "α-12",
                "β-12",
                "α-13",
                "β-13",
                "α-14",
                "β-14",
                "最終章",
                "尾聲",
            )
        ),
    ),
    BookSpec(
        book_id="v12-intuition",
        volume=12,
        filename="涼宮春日的直覺.txt",
        title="凉宫春日的直觉",
        sections=_sections(
            ("無厘數", "七大不可思議延長賽", "鶴屋學姊的挑戰"),
            timeline="surprise",
            spoiler_level=6,
        ),
    ),
    BookSpec(
        book_id="v13-theater",
        volume=13,
        filename="[谷川流]涼宮春日的劇場[系列Vol.13][繁].txt",
        title="凉宫春日的剧场",
        sections=_sections(
            ("act.1 奇幻篇", "act.2 銀河篇", "act.3 狂野之旅篇", "final act 脫逃篇"),
            timeline="surprise",
            spoiler_level=6,
        ),
    ),
)


CHARACTER_DISPLAY_NAMES: dict[str, str] = {
    "haruhi": "凉宫春日",
    "kyon": "阿虚",
    "mikuru": "朝比奈实玖瑠",
    "yuki": "长门有希",
    "itsuki": "古泉一树",
}


CHARACTER_ALIASES: dict[str, tuple[str, ...]] = {
    "haruhi": ("涼宮春日", "涼宮", "春日", "團長"),
    "kyon": ("阿虛",),
    "mikuru": ("朝比奈實玖瑠", "朝比奈", "實玖瑠"),
    "yuki": ("長門有希", "長門", "有希"),
    "itsuki": ("古泉一樹", "古泉"),
}
