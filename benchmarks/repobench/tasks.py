"""repobench — multi-file coding tasks that the single-function minibench can't measure.

Each task is a small repo (2-4 files) with a bug or gap that spans files, plus a
hidden test suite. The model gets ALL the files + the task, and must return the
complete corrected content of whatever files it changes. Scored by running the
hidden tests — all-or-nothing per task, no LLM judge.

This is the axis where local 30B and cloud/80B diverge: cross-file comprehension,
following existing patterns, fixing a symptom whose cause is in another file. The
minibench (isolated functions) saturated at 24/24; this one shouldn't.

Each task dict:
  id, prompt, files {path: buggy_content}, reference {path: fixed_content}, test (str)
The reference must pass the test; the buggy `files` must fail it (validated by the
harness before any model is scored — the bad-fixture discipline).
"""

TASKS = [
    # ---------------------------------------------------------------------------
    {
        "id": "registry_dispatch",
        "prompt": (
            "This package dispatches operations by name through a registry. Two "
            "operations ('add' and 'sub') are already registered. Add a new "
            "operation 'mul' that multiplies its two integer arguments, following "
            "the exact same registration pattern as the existing handlers. Do not "
            "change the dispatch mechanism. Return the complete content of any file "
            "you modify."
        ),
        "files": {
            "ops/base.py": (
                "REGISTRY = {}\n\n"
                "def register(name):\n"
                "    def deco(fn):\n"
                "        REGISTRY[name] = fn\n"
                "        return fn\n"
                "    return deco\n"
            ),
            "ops/handlers.py": (
                "from ops.base import register\n\n"
                "@register('add')\n"
                "def _add(a, b):\n"
                "    return a + b\n\n"
                "@register('sub')\n"
                "def _sub(a, b):\n"
                "    return a - b\n"
            ),
            "ops/dispatch.py": (
                "from ops.base import REGISTRY\n"
                "import ops.handlers  # noqa: F401  (populates REGISTRY)\n\n"
                "def dispatch(name, a, b):\n"
                "    if name not in REGISTRY:\n"
                "        raise KeyError(name)\n"
                "    return REGISTRY[name](a, b)\n"
            ),
        },
        "reference": {
            "ops/handlers.py": (
                "from ops.base import register\n\n"
                "@register('add')\n"
                "def _add(a, b):\n"
                "    return a + b\n\n"
                "@register('sub')\n"
                "def _sub(a, b):\n"
                "    return a - b\n\n"
                "@register('mul')\n"
                "def _mul(a, b):\n"
                "    return a * b\n"
            ),
        },
        "test": (
            "from ops.dispatch import dispatch\n"
            "def test_existing():\n"
            "    assert dispatch('add', 2, 3) == 5\n"
            "    assert dispatch('sub', 7, 4) == 3\n"
            "def test_mul():\n"
            "    assert dispatch('mul', 6, 7) == 42\n"
            "    assert dispatch('mul', 0, 9) == 0\n"
        ),
    },
    # ---------------------------------------------------------------------------
    {
        "id": "symptom_elsewhere",
        "prompt": (
            "validate(record) in rules.py returns a list of error strings. A record "
            "with a zero amount is being accepted when it should be rejected with the "
            "error 'amount must be positive'. The validation logic itself is correct; "
            "the bug is in one of the helper predicates it relies on. Find and fix the "
            "root cause so a zero (or negative) amount is rejected, without breaking "
            "positive amounts. Return the complete content of any file you modify."
        ),
        "files": {
            "checks.py": (
                "def is_positive(n):\n"
                "    # BUG: zero is not positive\n"
                "    return n >= 0\n\n"
                "def is_nonempty(s):\n"
                "    return isinstance(s, str) and len(s) > 0\n"
            ),
            "rules.py": (
                "from checks import is_positive, is_nonempty\n\n"
                "def validate(record):\n"
                "    errors = []\n"
                "    if not is_nonempty(record.get('name', '')):\n"
                "        errors.append('name is required')\n"
                "    if not is_positive(record.get('amount', 0)):\n"
                "        errors.append('amount must be positive')\n"
                "    return errors\n"
            ),
        },
        "reference": {
            "checks.py": (
                "def is_positive(n):\n"
                "    return n > 0\n\n"
                "def is_nonempty(s):\n"
                "    return isinstance(s, str) and len(s) > 0\n"
            ),
        },
        "test": (
            "from rules import validate\n"
            "def test_zero_rejected():\n"
            "    assert 'amount must be positive' in validate({'name':'x','amount':0})\n"
            "def test_negative_rejected():\n"
            "    assert 'amount must be positive' in validate({'name':'x','amount':-5})\n"
            "def test_positive_ok():\n"
            "    assert validate({'name':'x','amount':10}) == []\n"
            "def test_name_still_checked():\n"
            "    assert 'name is required' in validate({'name':'','amount':10})\n"
        ),
    },
    # ---------------------------------------------------------------------------
    {
        "id": "cache_invalidation",
        "prompt": (
            "Store (store.py) caches reads through an LRUCache (lru.py). After put(key, "
            "value) updates a key, a subsequent get(key) returns the STALE cached value "
            "instead of the new one, because put() doesn't invalidate the cache. Fix it "
            "so get() always returns the latest written value, while keeping the cache "
            "working for repeated reads of unchanged keys. Return the complete content of "
            "any file you modify."
        ),
        "files": {
            "lru.py": (
                "from collections import OrderedDict\n\n"
                "class LRUCache:\n"
                "    def __init__(self, cap=128):\n"
                "        self.cap = cap\n"
                "        self.d = OrderedDict()\n"
                "    def get(self, k):\n"
                "        if k not in self.d:\n"
                "            return None\n"
                "        self.d.move_to_end(k)\n"
                "        return self.d[k]\n"
                "    def set(self, k, v):\n"
                "        self.d[k] = v\n"
                "        self.d.move_to_end(k)\n"
                "        if len(self.d) > self.cap:\n"
                "            self.d.popitem(last=False)\n"
                "    def invalidate(self, k):\n"
                "        self.d.pop(k, None)\n"
            ),
            "store.py": (
                "from lru import LRUCache\n\n"
                "class Store:\n"
                "    def __init__(self):\n"
                "        self._data = {}\n"
                "        self._cache = LRUCache()\n"
                "        self.reads = 0\n"
                "    def put(self, k, v):\n"
                "        self._data[k] = v\n"
                "        # BUG: cache not invalidated on write\n"
                "    def get(self, k):\n"
                "        c = self._cache.get(k)\n"
                "        if c is not None:\n"
                "            return c\n"
                "        self.reads += 1\n"
                "        v = self._data.get(k)\n"
                "        if v is not None:\n"
                "            self._cache.set(k, v)\n"
                "        return v\n"
            ),
        },
        "reference": {
            "store.py": (
                "from lru import LRUCache\n\n"
                "class Store:\n"
                "    def __init__(self):\n"
                "        self._data = {}\n"
                "        self._cache = LRUCache()\n"
                "        self.reads = 0\n"
                "    def put(self, k, v):\n"
                "        self._data[k] = v\n"
                "        self._cache.invalidate(k)\n"
                "    def get(self, k):\n"
                "        c = self._cache.get(k)\n"
                "        if c is not None:\n"
                "            return c\n"
                "        self.reads += 1\n"
                "        v = self._data.get(k)\n"
                "        if v is not None:\n"
                "            self._cache.set(k, v)\n"
                "        return v\n"
            ),
        },
        "test": (
            "from store import Store\n"
            "def test_fresh_after_update():\n"
            "    s = Store()\n"
            "    s.put('a', 1)\n"
            "    assert s.get('a') == 1\n"
            "    s.put('a', 2)\n"
            "    assert s.get('a') == 2\n"
            "def test_cache_still_works():\n"
            "    s = Store()\n"
            "    s.put('b', 9)\n"
            "    s.get('b'); s.get('b'); s.get('b')\n"
            "    assert s.reads == 1  # only one backing read for repeated unchanged gets\n"
        ),
    },
    # ---------------------------------------------------------------------------
    {
        "id": "shared_refactor",
        "prompt": (
            "report.py and invoice.py each contain an identical, duplicated helper that "
            "formats a cents integer as a dollar string (e.g. 1234 -> '$12.34'). Refactor "
            "by extracting that logic into a new module money.py as a function "
            "`format_cents(cents)`, and update both report.py and invoice.py to import and "
            "use it. Behavior must be unchanged and all tests must pass. Return the complete "
            "content of every file you create or modify."
        ),
        "files": {
            "report.py": (
                "def _fmt(cents):\n"
                "    return f\"${cents // 100}.{cents % 100:02d}\"\n\n"
                "def line_total(qty, unit_cents):\n"
                "    return _fmt(qty * unit_cents)\n"
            ),
            "invoice.py": (
                "def _fmt(cents):\n"
                "    return f\"${cents // 100}.{cents % 100:02d}\"\n\n"
                "def grand_total(line_cents):\n"
                "    return _fmt(sum(line_cents))\n"
            ),
        },
        "reference": {
            "money.py": (
                "def format_cents(cents):\n"
                "    return f\"${cents // 100}.{cents % 100:02d}\"\n"
            ),
            "report.py": (
                "from money import format_cents\n\n"
                "def line_total(qty, unit_cents):\n"
                "    return format_cents(qty * unit_cents)\n"
            ),
            "invoice.py": (
                "from money import format_cents\n\n"
                "def grand_total(line_cents):\n"
                "    return format_cents(sum(line_cents))\n"
            ),
        },
        "test": (
            "import importlib\n"
            "def test_module_exists():\n"
            "    m = importlib.import_module('money')\n"
            "    assert m.format_cents(1234) == '$12.34'\n"
            "    assert m.format_cents(5) == '$0.05'\n"
            "def test_report_uses_it():\n"
            "    from report import line_total\n"
            "    assert line_total(3, 499) == '$14.97'\n"
            "def test_invoice_uses_it():\n"
            "    from invoice import grand_total\n"
            "    assert grand_total([100, 250, 99]) == '$4.49'\n"
            "def test_no_duplicate_helper():\n"
            "    # both modules must delegate, not redefine the formatter\n"
            "    import report, invoice\n"
            "    assert not hasattr(report, '_fmt'), 'report still has its own _fmt'\n"
            "    assert not hasattr(invoice, '_fmt'), 'invoice still has its own _fmt'\n"
        ),
    },
]
