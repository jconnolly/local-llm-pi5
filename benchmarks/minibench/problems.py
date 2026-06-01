"""Mini-bench problem set — HumanEval-style, deterministic hidden tests.

12 problems, easy -> hard, each self-contained with a function signature and a
test battery. Scored by executing the model's code against the tests — no
LLM-judge (dodges the Act 13 Maral-capacity failure). Same problems run on
local (qwen3:8b tuned) and cloud (Opus 4.8) for a fair head-to-head.

Each problem: {id, difficulty, prompt, entrypoint, tests: [(args, expected)]}.
Tests call entrypoint(*args) and compare == expected.
"""

PROBLEMS = [
    {
        "id": "is_balanced", "difficulty": "easy",
        "prompt": "Write `is_balanced(s)` returning True if brackets ()[]{} in string s are balanced, else False.",
        "entrypoint": "is_balanced",
        "tests": [(("()",), True), (("([])",), True), (("([)]",), False),
                  (("(((",), False), (("{[()]}",), True), (("",), True),
                  ((")(",), False), (("a(b)c",), True), (("[(])",), False)],
    },
    {
        "id": "two_sum", "difficulty": "easy",
        "prompt": "Write `two_sum(nums, target)` returning indices [i, j] (i<j) of the two numbers that add to target. Exactly one solution exists. Return a list of two ints.",
        "entrypoint": "two_sum",
        "tests": [(([2,7,11,15], 9), [0,1]), (([3,2,4], 6), [1,2]),
                  (([3,3], 6), [0,1]), (([1,5,3,7], 12), [1,3])],
    },
    {
        "id": "roman_to_int", "difficulty": "easy",
        "prompt": "Write `roman_to_int(s)` converting a Roman numeral string to an integer (1..3999).",
        "entrypoint": "roman_to_int",
        "tests": [(("III",), 3), (("IV",), 4), (("IX",), 9), (("LVIII",), 58),
                  (("MCMXCIV",), 1994), (("MMXXVI",), 2026)],
    },
    {
        "id": "merge_intervals", "difficulty": "medium",
        "prompt": "Write `merge_intervals(intervals)` that merges overlapping intervals. Input/output are lists of [start, end] pairs, output sorted by start.",
        "entrypoint": "merge_intervals",
        "tests": [(([[1,3],[2,6],[8,10],[15,18]],), [[1,6],[8,10],[15,18]]),
                  (([[1,4],[4,5]],), [[1,5]]),
                  (([[1,4],[2,3]],), [[1,4]]),
                  (([[1,4]],), [[1,4]])],
    },
    {
        "id": "longest_unique", "difficulty": "medium",
        "prompt": "Write `longest_unique(s)` returning the length of the longest substring of s without repeating characters.",
        "entrypoint": "longest_unique",
        "tests": [(("abcabcbb",), 3), (("bbbbb",), 1), (("pwwkew",), 3),
                  (("",), 0), (("dvdf",), 3), (("abba",), 2)],
    },
    {
        "id": "spiral_order", "difficulty": "medium",
        "prompt": "Write `spiral_order(matrix)` returning all elements of the 2D matrix in spiral order as a flat list.",
        "entrypoint": "spiral_order",
        "tests": [(([[1,2,3],[4,5,6],[7,8,9]],), [1,2,3,6,9,8,7,4,5]),
                  (([[1,2,3,4],[5,6,7,8],[9,10,11,12]],), [1,2,3,4,8,12,11,10,9,5,6,7]),
                  (([[1]],), [1]), (([[1,2],[3,4]],), [1,2,4,3])],
    },
    {
        "id": "word_break", "difficulty": "hard",
        "prompt": "Write `word_break(s, word_dict)` returning True if s can be segmented into a space-separated sequence of one or more words from the list word_dict (words reusable).",
        "entrypoint": "word_break",
        "tests": [(("leetcode", ["leet","code"]), True),
                  (("applepenapple", ["apple","pen"]), True),
                  (("catsandog", ["cats","dog","sand","and","cat"]), False),
                  (("aaaaaaa", ["aaaa","aaa"]), True)],
    },
    {
        "id": "coin_change", "difficulty": "hard",
        "prompt": "Write `coin_change(coins, amount)` returning the fewest number of coins to make amount, or -1 if impossible.",
        "entrypoint": "coin_change",
        "tests": [(([1,2,5], 11), 3), (([2], 3), -1), (([1], 0), 0),
                  (([1,2,5], 100), 20), (([186,419,83,408], 6249), 20)],
    },
    {
        "id": "lru_cache", "difficulty": "hard",
        "prompt": ("Write a class `LRUCache` with __init__(self, capacity), get(self, key) "
                   "returning value or -1, and put(self, key, value). Evicts least-recently-used "
                   "when over capacity. get and put both count as use."),
        "entrypoint": "__LRUCACHE__",  # special-cased in harness
        "tests": [],  # see harness lru test
    },
    {
        "id": "edit_distance", "difficulty": "hard",
        "prompt": "Write `edit_distance(a, b)` returning the Levenshtein edit distance (min insert/delete/replace ops) between strings a and b.",
        "entrypoint": "edit_distance",
        "tests": [(("horse","ros"), 3), (("intention","execution"), 5),
                  (("","abc"), 3), (("same","same"), 0), (("a","b"), 1)],
    },
    {
        "id": "trap_rain", "difficulty": "hard",
        "prompt": "Write `trap_rain(height)` returning total trapped rainwater given a list of non-negative bar heights.",
        "entrypoint": "trap_rain",
        "tests": [(([0,1,0,2,1,0,1,3,2,1,2,1],), 6), (([4,2,0,3,2,5],), 9),
                  (([],), 0), (([1,2,3],), 0), (([3,2,1],), 0)],
    },
    {
        "id": "median_two_sorted", "difficulty": "hard",
        "prompt": "Write `median_two_sorted(a, b)` returning the median (float) of two sorted lists a and b combined.",
        "entrypoint": "median_two_sorted",
        "tests": [(([1,3],[2]), 2.0), (([1,2],[3,4]), 2.5),
                  (([],[1]), 1.0), (([1,2,3,4,5,6],[7,8]), 4.5)],
    },
]
