"""The exact metadata IDs and dimensions of Archyar's Android furniture catalog.

Source: MaxLightner/archyar FurnitureCatalog.java at main, 2026-10-23.
Models are lightweight procedural reconstructions, not extracted GLB assets.
"""

from dataclasses import dataclass


SOURCE_REPOSITORY = "MaxLightner/archyar"
FURNITURE_ORIGIN = "chido-procedural-v0.5"
PALETTE = ((.714, .737, .635), (.835, .769, .678), (.725, .769, .776), (.729, .576, .502))


@dataclass(frozen=True)
class Asset:
    index: int
    name: str
    category: str
    template: str
    width: float
    height: float
    depth: float
    wall_mounted: bool = False


FURNITURE = (
    Asset(0, "کاناپه", "seating", "sofa", 2.10, .85, .90),
    Asset(1, "تک‌نفره", "seating", "armchair", .90, .85, .90),
    Asset(2, "میز", "tables", "table", 1.10, .40, .60),
    Asset(3, "تک‌نفره دوم", "seating", "armchair", .90, .85, .90),
    Asset(4, "گلدان سرامیکی", "decor", "vase", .25, .40, .25),
    Asset(5, "کوسن دکوراتیو", "decor", "pillow", .46, .18, .40),
    Asset(6, "آباژور ایستاده", "lighting", "floor-lamp", .45, 1.55, .45),
    Asset(7, "فرش مینیمال", "rugs", "rug", 2.40, .015, 1.70),
    Asset(8, "تخت دو نفره", "bedroom", "bed", 1.65, .95, 2.08),
    Asset(9, "میز کار", "workspace", "desk", 1.40, .74, .67),
    Asset(10, "میز ناهارخوری", "dining", "dining-table", 1.70, .75, .86),
    Asset(11, "صندلی ناهارخوری", "dining", "chair", .48, .90, .47),
    Asset(12, "میز عسلی مربعی", "tables", "side-table", .48, .48, .48),
    Asset(13, "میز جلو مبلی مربعی", "tables", "coffee-table", 1.15, .42, 1.15),
    Asset(14, "آباژور رومیزی", "lighting", "desk-lamp", .35, .55, .35),
    Asset(15, "آباژور سه‌پایه", "lighting", "tripod-lamp", .55, 1.60, .55),
    Asset(16, "تابلو عمودی کوچک", "wall-art", "art", .45, .68, .045, True),
    Asset(17, "تابلو افقی کوچک", "wall-art", "art", .70, .44, .045, True),
    Asset(18, "تابلو مربعی متوسط", "wall-art", "art", .65, .65, .045, True),
    Asset(19, "تابلو افقی بزرگ", "wall-art", "art", 1.20, .68, .045, True),
    Asset(20, "تابلو عمودی بزرگ", "wall-art", "art", .78, 1.15, .045, True),
    Asset(21, "تابلو سه‌تکه", "wall-art", "triptych", 1.25, .75, .045, True),
)

CATEGORY_NAMES = {
    "seating": "نشیمن", "tables": "میزها", "decor": "دکور", "lighting": "روشنایی",
    "rugs": "فرش", "bedroom": "اتاق خواب", "workspace": "میز کار",
    "dining": "غذاخوری", "wall-art": "تابلو دیواری",
}
WALL_PRESETS = {"wall": ("دیوار هبلکس", .15), "partition": ("تیغه داخلی", .10), "block": ("دیوار بلوکی", .20)}
OPENINGS = {"fixed": "پنجره ثابت", "sliding": "پنجره کشویی", "hinged": "پنجره لولایی", "arched": "پنجره قوسی", "door": "در لولایی", "sliding-door": "در کشویی"}
BUILD_PARTS = {"column": "ستون", "floor": "کف", "ceiling": "سقف", "stairs": "پله مستقیم", "railing": "نرده"}


def furniture(index):
    if not isinstance(index, int) or not 0 <= index < len(FURNITURE):
        raise ValueError("Unknown Archyar furniture index")
    return FURNITURE[index]


def validate_catalog():
    assert len(FURNITURE) == 22
    assert [a.index for a in FURNITURE] == list(range(22))
    assert all(a.width > 0 and a.height > 0 and a.depth > 0 for a in FURNITURE)


validate_catalog()
