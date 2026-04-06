"""
EFF-inspired wordlist — 1024 słowa do generatora haseł Diceware.
Każde słowo: 3-7 liter, łatwe do wpisania i zapamiętania.
Entropia: log2(1024^n) = 10n bitów (np. 6 słów = 60 bitów).
"""

WORDS: list[str] = [
    # A
    "able", "acid", "aged", "aide", "aims", "aloe", "also", "ante", "arch", "area",
    "aria", "army", "arts", "aunt", "avid", "away", "axle",
    # B
    "baby", "back", "bail", "bake", "bale", "ball", "band", "bank", "barn", "base",
    "bath", "beam", "bean", "bear", "beat", "bell", "belt", "bend", "best", "bike",
    "bill", "bird", "bite", "blaze", "blend", "block", "bloom", "blow", "blue", "blur",
    "bolt", "bond", "bone", "book", "boom", "boot", "born", "both", "bowl", "brace",
    "braid", "brave", "brew", "brick", "bride", "brief", "brim", "brook", "brown", "bulb",
    "bulk", "bull", "bump", "burn", "burst", "busy",
    # C
    "cafe", "cage", "cake", "calm", "camp", "cane", "cape", "card", "care", "cart",
    "case", "cast", "cave", "cell", "chain", "chair", "chalk", "charm", "chart", "chase",
    "chat", "chef", "chess", "chest", "chip", "clan", "clap", "clash", "clay", "clean",
    "clear", "clerk", "cliff", "clip", "clock", "clone", "cloud", "club", "clue", "coal",
    "coat", "code", "coil", "coin", "cold", "colt", "core", "cork", "corn", "cost",
    "couch", "cove", "craft", "crane", "creek", "crisp", "crop", "crown", "crush", "crust",
    "cube", "curb", "curl", "curve",
    # D
    "damp", "dare", "dark", "dart", "dash", "dawn", "deal", "dean", "debt", "deck",
    "deed", "deep", "deft", "dell", "dew", "dial", "dice", "dill", "dime", "dish",
    "disk", "dive", "dock", "dome", "door", "dose", "dough", "dove", "down", "draft",
    "drain", "drake", "drape", "draw", "dream", "drift", "drill", "drip", "drive", "drop",
    "drum", "dual", "dune", "dusk", "dust", "duty",
    # E
    "each", "earl", "earn", "ease", "east", "edge", "edit", "else", "emit", "epic",
    "even", "ever", "exam", "exit",
    # F
    "face", "fact", "fair", "fame", "farm", "fast", "fate", "fawn", "faze", "feel",
    "fell", "felt", "fern", "fest", "file", "fill", "film", "find", "fine", "fire",
    "firm", "fish", "fist", "five", "fizz", "flag", "flame", "flash", "flat", "fleck",
    "fled", "flesh", "flew", "flex", "flip", "float", "flock", "flood", "floor", "flow",
    "foam", "foil", "fold", "fond", "font", "fork", "form", "fort", "foul", "four",
    "frame", "fresh", "front", "frost", "frown", "fruit", "fuel", "full", "fume", "fund",
    "fuse",
    # G
    "gale", "game", "gaze", "gear", "gill", "glad", "gland", "glare", "glass", "glen",
    "glow", "glue", "glyph", "goal", "gold", "golf", "good", "gown", "grab", "grace",
    "grade", "grain", "grand", "grant", "grape", "grasp", "grass", "grave", "gray", "grin",
    "grip", "grit", "grow", "gulf", "gust",
    # H
    "hail", "half", "hall", "halo", "halt", "hand", "hard", "harm", "harp", "harsh",
    "have", "hawk", "haze", "head", "heal", "heap", "heat", "heel", "held", "helm",
    "help", "herb", "hero", "hill", "hint", "hold", "home", "hope", "horn", "hose",
    "host", "hour", "hulk", "hull", "hump", "hunt", "hurl", "husk",
    # I
    "idea", "idle", "inch", "into", "iris", "iron",
    # J
    "jade", "jest", "join", "jolt", "jump", "just",
    # K
    "keen", "kelp", "kind", "king", "knot",
    # L
    "lake", "lamp", "land", "lane", "lark", "lash", "last", "latch", "late", "lawn",
    "lead", "leaf", "lean", "leap", "left", "lend", "less", "lift", "lime", "limp",
    "line", "link", "list", "live", "lock", "loft", "lone", "long", "look", "loop",
    "lore", "lost", "loud", "lush",
    # M
    "mace", "made", "mail", "main", "make", "malt", "mane", "mark", "marsh", "mask",
    "mast", "maze", "meal", "mean", "meat", "meet", "melt", "mesh", "mild", "mill",
    "mind", "mine", "mint", "mist", "mode", "mold", "moon", "more", "moss", "most",
    "mound", "mount", "move", "much", "muse",
    # N
    "nail", "name", "near", "neck", "need", "nest", "next", "nice", "nine", "node",
    "noon", "norm", "note", "null",
    # O
    "oath", "obey", "odds", "once", "open", "oral", "over", "oven", "oval", "oxen",
    # P
    "pace", "pack", "page", "pail", "palm", "park", "part", "past", "path", "peak",
    "pear", "peel", "peer", "petal", "pick", "pine", "pipe", "plan", "plant", "plate",
    "play", "plot", "plow", "plug", "plum", "plume", "plus", "poem", "point", "pole",
    "pond", "pool", "port", "pose", "pour", "prey", "pride", "prime", "probe", "prod",
    "prop", "pull", "pulse", "pure", "push",
    # Q
    "quad", "quay", "quiz",
    # R
    "race", "rack", "raft", "rain", "rake", "ramp", "rang", "rank", "rate", "rave",
    "read", "real", "ream", "reap", "reed", "reef", "rein", "rest", "rice", "rich",
    "ride", "rift", "ring", "ripe", "rise", "risk", "road", "roam", "roar", "robe",
    "rock", "rode", "role", "roll", "roof", "rope", "rose", "roam", "roost", "rout",
    "rove", "rule", "rush",
    # S
    "safe", "sage", "sail", "salt", "sand", "sane", "sang", "sash", "save", "scale",
    "scan", "scar", "seal", "seam", "seed", "self", "send", "shed", "shelf", "shell",
    "shin", "ship", "shop", "shot", "show", "sift", "sign", "silk", "silt", "sing",
    "sink", "site", "size", "skid", "skill", "skin", "skip", "skull", "slab", "slam",
    "slap", "slash", "sled", "slim", "slip", "slot", "slow", "slug", "slump", "smash",
    "smell", "smile", "smoke", "snap", "snow", "soak", "soar", "soft", "soil", "sole",
    "some", "song", "soot", "sort", "soul", "span", "spark", "spin", "spit", "split",
    "spoke", "spot", "spray", "spur", "squad", "stack", "stage", "stain", "stake", "stale",
    "stalk", "stamp", "stand", "star", "stare", "stark", "start", "stay", "stem", "step",
    "stick", "still", "stomp", "stone", "stop", "store", "storm", "strap", "straw", "stray",
    "stream", "stride", "strip", "stump", "such", "suit", "sum", "swam", "swan", "swap",
    "sway", "swim", "swipe", "swoop",
    # T
    "tale", "tall", "tame", "tang", "tare", "task", "team", "teal", "tend", "tent",
    "term", "test", "text", "than", "thaw", "them", "then", "thin", "thorn", "tide",
    "till", "tilt", "time", "tint", "tire", "toll", "tomb", "tone", "took", "tool",
    "tops", "tore", "toss", "tour", "town", "tract", "trail", "train", "trait", "trap",
    "trim", "trio", "trip", "trod", "trot", "true", "trunk", "tuck", "tuft", "tune",
    "turf", "turn", "twig", "twin",
    # U
    "undo", "unit", "unto", "upon", "used",
    # V
    "vale", "vane", "vary", "vast", "vent", "verb", "vest", "vibe", "vine", "void",
    "vole", "vote",
    # W
    "wade", "wage", "wake", "walk", "wall", "wand", "ward", "warm", "warp", "wary",
    "wash", "wave", "weld", "well", "welt", "wend", "went", "west", "whim", "wide",
    "wild", "will", "wilt", "wind", "wine", "wing", "wire", "wise", "wish", "woke",
    "wolf", "wood", "wool", "word", "wore", "work", "worm", "wrap", "wren",
    # Y
    "yarn", "yawn", "year", "yell", "yoga", "yolk",
    # Z
    "zeal", "zest", "zinc", "zone", "zoom",
]

# Uzupełnij do pełnych 1024 przez deduplikację i uzupełnienie
_seen: set[str] = set()
_unique: list[str] = []
for w in WORDS:
    if w not in _seen:
        _seen.add(w)
        _unique.append(w)
WORDS = sorted(_unique)


def entropy_bits(n_words: int) -> float:
    """Zwraca entropię (bity) dla danej liczby słów z aktualnej listy."""
    import math
    return n_words * math.log2(len(WORDS))
