"""repobench HARD set — subtle boundary bugs spanning files. Each buggy version
PASSES the naive cases and FAILS only on a specific edge condition, so finding it
requires actually understanding the cross-file logic, not pattern-matching. These
are the tasks meant to separate a 30B from an 80B coder / Opus.

Run:  TASKS_MODULE=tasks_hard MINIBENCH_MODEL=... python harness.py run
"""

TASKS = [
    # 1. Pagination misses the final partial page — only wrong when total isn't an
    #    exact multiple of page size. Cause in pager.py; symptom (wrong count) in count.py.
    {
        "id": "pagination_partial_page",
        "prompt": (
            "count_items(data, page_size) is returning the wrong total for some inputs. "
            "It paginates through `data` via fetch_all() in pager.py and counts what it "
            "gets. The counts are correct when len(data) is an exact multiple of page_size "
            "but short otherwise. Find and fix the root cause. Behavior for the multiple "
            "case must stay correct."
        ),
        "files": {
            "pager.py": (
                "def fetch_all(fetch_page, page_size):\n"
                "    items = []\n"
                "    offset = 0\n"
                "    page = fetch_page(offset, page_size)\n"
                "    while len(page) == page_size:\n"
                "        items.extend(page)\n"
                "        offset += page_size\n"
                "        page = fetch_page(offset, page_size)\n"
                "    # the final (partial) page is never added\n"
                "    return items\n"
            ),
            "count.py": (
                "from pager import fetch_all\n\n"
                "def count_items(data, page_size):\n"
                "    def fetch_page(offset, limit):\n"
                "        return data[offset:offset + limit]\n"
                "    return len(fetch_all(fetch_page, page_size))\n"
            ),
        },
        "reference": {
            "pager.py": (
                "def fetch_all(fetch_page, page_size):\n"
                "    items = []\n"
                "    offset = 0\n"
                "    while True:\n"
                "        page = fetch_page(offset, page_size)\n"
                "        items.extend(page)\n"
                "        if len(page) < page_size:\n"
                "            break\n"
                "        offset += page_size\n"
                "    return items\n"
            ),
        },
        "test": (
            "from count import count_items\n"
            "def test_exact_multiple():\n"
            "    assert count_items(list(range(9)), 3) == 9\n"
            "    assert count_items(list(range(12)), 4) == 12\n"
            "def test_partial_last_page():\n"
            "    assert count_items(list(range(10)), 3) == 10\n"
            "    assert count_items(list(range(7)), 5) == 7\n"
            "def test_single_short_page():\n"
            "    assert count_items([1, 2], 5) == 2\n"
            "def test_empty():\n"
            "    assert count_items([], 4) == 0\n"
        ),
    },

    # 2. TTL cache: expiry uses > so an entry survives one tick too long. Cross-file:
    #    clock.py supplies time; ttlcache.py decides validity. Boundary-only failure.
    {
        "id": "ttl_off_by_one",
        "prompt": (
            "TTLCache (ttlcache.py) reads time from a Clock (clock.py). An entry with "
            "ttl=T should be considered EXPIRED once exactly T units have elapsed since it "
            "was set (i.e. age >= T means gone). Right now an entry is still returned at "
            "age == T and only disappears at age T+1. Fix the expiry boundary without "
            "breaking entries that are still within their ttl."
        ),
        "files": {
            "clock.py": (
                "class Clock:\n"
                "    def __init__(self):\n"
                "        self.t = 0\n"
                "    def now(self):\n"
                "        return self.t\n"
                "    def advance(self, n=1):\n"
                "        self.t += n\n"
            ),
            "ttlcache.py": (
                "class TTLCache:\n"
                "    def __init__(self, clock):\n"
                "        self.clock = clock\n"
                "        self.store = {}\n"
                "    def set(self, key, value, ttl):\n"
                "        self.store[key] = (value, self.clock.now(), ttl)\n"
                "    def get(self, key):\n"
                "        if key not in self.store:\n"
                "            return None\n"
                "        value, ts, ttl = self.store[key]\n"
                "        age = self.clock.now() - ts\n"
                "        if age > ttl:\n"
                "            del self.store[key]\n"
                "            return None\n"
                "        return value\n"
            ),
        },
        "reference": {
            "ttlcache.py": (
                "class TTLCache:\n"
                "    def __init__(self, clock):\n"
                "        self.clock = clock\n"
                "        self.store = {}\n"
                "    def set(self, key, value, ttl):\n"
                "        self.store[key] = (value, self.clock.now(), ttl)\n"
                "    def get(self, key):\n"
                "        if key not in self.store:\n"
                "            return None\n"
                "        value, ts, ttl = self.store[key]\n"
                "        age = self.clock.now() - ts\n"
                "        if age >= ttl:\n"
                "            del self.store[key]\n"
                "            return None\n"
                "        return value\n"
            ),
        },
        "test": (
            "from clock import Clock\n"
            "from ttlcache import TTLCache\n"
            "def test_within_ttl():\n"
            "    c = Clock(); cache = TTLCache(c)\n"
            "    cache.set('k', 'v', 3)\n"
            "    c.advance(2)\n"
            "    assert cache.get('k') == 'v'\n"
            "def test_expires_at_boundary():\n"
            "    c = Clock(); cache = TTLCache(c)\n"
            "    cache.set('k', 'v', 3)\n"
            "    c.advance(3)\n"
            "    assert cache.get('k') is None\n"
            "def test_fresh_zero_age():\n"
            "    c = Clock(); cache = TTLCache(c)\n"
            "    cache.set('k', 'v', 1)\n"
            "    assert cache.get('k') == 'v'\n"
            "    c.advance(1)\n"
            "    assert cache.get('k') is None\n"
        ),
    },

    # 3. Retry attempt accounting: max_retries is RETRIES after the first attempt, so
    #    total attempts == max_retries + 1. Buggy stops one attempt early. Cross-file.
    {
        "id": "retry_off_by_one",
        "prompt": (
            "with_retries(fn, max_retries) in retry.py should call fn until it succeeds or "
            "the retries are exhausted. The contract: max_retries is the number of RETRIES "
            "after the initial attempt, so a function that needs 3 total attempts must "
            "succeed with max_retries=2. Right now such a function raises instead. Fix the "
            "attempt counting. Do not change backoff.py."
        ),
        "files": {
            "backoff.py": (
                "def delay_for(attempt):\n"
                "    # attempt is 0-based; pure function, no sleeping in tests\n"
                "    return 2 ** attempt\n"
            ),
            "retry.py": (
                "from backoff import delay_for\n\n"
                "class RetryError(Exception):\n"
                "    pass\n\n"
                "def with_retries(fn, max_retries):\n"
                "    attempts = 0\n"
                "    last = None\n"
                "    while attempts < max_retries:\n"
                "        try:\n"
                "            return fn()\n"
                "        except Exception as e:\n"
                "            last = e\n"
                "            _ = delay_for(attempts)\n"
                "            attempts += 1\n"
                "    raise RetryError(str(last))\n"
            ),
        },
        "reference": {
            "retry.py": (
                "from backoff import delay_for\n\n"
                "class RetryError(Exception):\n"
                "    pass\n\n"
                "def with_retries(fn, max_retries):\n"
                "    attempts = 0\n"
                "    last = None\n"
                "    while attempts <= max_retries:\n"
                "        try:\n"
                "            return fn()\n"
                "        except Exception as e:\n"
                "            last = e\n"
                "            _ = delay_for(attempts)\n"
                "            attempts += 1\n"
                "    raise RetryError(str(last))\n"
            ),
        },
        "test": (
            "import pytest\n"
            "from retry import with_retries, RetryError\n"
            "def make_fn(succeed_on):\n"
            "    calls = {'n': 0}\n"
            "    def fn():\n"
            "        calls['n'] += 1\n"
            "        if calls['n'] >= succeed_on:\n"
            "            return 'ok'\n"
            "        raise ValueError('not yet')\n"
            "    fn.calls = calls\n"
            "    return fn\n"
            "def test_succeeds_on_last_retry():\n"
            "    fn = make_fn(3)  # needs 3 total attempts\n"
            "    assert with_retries(fn, 2) == 'ok'\n"
            "    assert fn.calls['n'] == 3\n"
            "def test_first_try():\n"
            "    fn = make_fn(1)\n"
            "    assert with_retries(fn, 2) == 'ok'\n"
            "    assert fn.calls['n'] == 1\n"
            "def test_exhausts():\n"
            "    fn = make_fn(99)\n"
            "    with pytest.raises(RetryError):\n"
            "        with_retries(fn, 2)\n"
            "    assert fn.calls['n'] == 3  # initial + 2 retries\n"
        ),
    },

    # 4. Interval merge: touching intervals ([1,2],[2,3]) must merge (closed intervals).
    #    Buggy uses strict overlap so touching stay separate; also must handle unsorted.
    {
        "id": "interval_touching_merge",
        "prompt": (
            "merge_all(intervals) in merge.py merges a list of closed integer intervals "
            "[start, end]. Two bugs: (a) intervals that merely TOUCH, like [1,2] and [2,3], "
            "are left separate but should merge into [1,3]; (b) it assumes the input is "
            "already sorted and produces wrong results when it isn't. Fix both. The overlap "
            "predicate lives in interval.py."
        ),
        "files": {
            "interval.py": (
                "def overlaps(a, b):\n"
                "    # a, b are [start, end] closed intervals\n"
                "    return a[1] > b[0] and b[1] > a[0]\n"
            ),
            "merge.py": (
                "from interval import overlaps\n\n"
                "def merge_all(intervals):\n"
                "    out = []\n"
                "    for iv in intervals:\n"
                "        if out and overlaps(out[-1], iv):\n"
                "            out[-1] = [min(out[-1][0], iv[0]), max(out[-1][1], iv[1])]\n"
                "        else:\n"
                "            out.append(list(iv))\n"
                "    return out\n"
            ),
        },
        "reference": {
            "interval.py": (
                "def overlaps(a, b):\n"
                "    # closed intervals: touching endpoints count as overlapping\n"
                "    return a[1] >= b[0] and b[1] >= a[0]\n"
            ),
            "merge.py": (
                "from interval import overlaps\n\n"
                "def merge_all(intervals):\n"
                "    out = []\n"
                "    for iv in sorted(intervals, key=lambda x: x[0]):\n"
                "        if out and overlaps(out[-1], iv):\n"
                "            out[-1] = [min(out[-1][0], iv[0]), max(out[-1][1], iv[1])]\n"
                "        else:\n"
                "            out.append(list(iv))\n"
                "    return out\n"
            ),
        },
        "test": (
            "from merge import merge_all\n"
            "def test_touching_merges():\n"
            "    assert merge_all([[1, 2], [2, 3]]) == [[1, 3]]\n"
            "def test_overlapping():\n"
            "    assert merge_all([[1, 4], [2, 5]]) == [[1, 5]]\n"
            "def test_disjoint_stays():\n"
            "    assert merge_all([[1, 2], [4, 5]]) == [[1, 2], [4, 5]]\n"
            "def test_unsorted_input():\n"
            "    assert merge_all([[5, 6], [1, 2], [2, 4]]) == [[1, 4], [5, 6]]\n"
        ),
    },

    # 5. Diamond dependency double-counts shared transitive deps in a cost rollup.
    #    Bug: a dependency reachable via two paths is summed twice. Cross-file:
    #    graph.py walks deps, cost.py sums weights — only wrong on diamond shapes.
    {
        "id": "diamond_double_count",
        "prompt": (
            "total_cost(deps, weights) in cost.py sums the weight of a package plus all of "
            "its transitive dependencies, each counted ONCE. It's over-counting when the "
            "dependency graph is a diamond (a package reachable through two different paths "
            "gets added twice). Fix it so every distinct dependency contributes exactly once. "
            "The dependency walk lives in graph.py."
        ),
        "files": {
            "graph.py": (
                "def walk_deps(pkg, deps):\n"
                "    # yield pkg and every transitive dependency (may repeat on diamonds)\n"
                "    yield pkg\n"
                "    for d in deps.get(pkg, []):\n"
                "        yield from walk_deps(d, deps)\n"
            ),
            "cost.py": (
                "from graph import walk_deps\n\n"
                "def total_cost(deps, weights):\n"
                "    def cost(pkg):\n"
                "        return sum(weights[p] for p in walk_deps(pkg, deps))\n"
                "    return {pkg: cost(pkg) for pkg in deps}\n"
            ),
        },
        "reference": {
            "cost.py": (
                "from graph import walk_deps\n\n"
                "def total_cost(deps, weights):\n"
                "    def cost(pkg):\n"
                "        return sum(weights[p] for p in set(walk_deps(pkg, deps)))\n"
                "    return {pkg: cost(pkg) for pkg in deps}\n"
            ),
        },
        "test": (
            "from cost import total_cost\n"
            "def test_linear_chain():\n"
            "    deps = {'a': ['b'], 'b': ['c'], 'c': []}\n"
            "    w = {'a': 1, 'b': 2, 'c': 4}\n"
            "    assert total_cost(deps, w)['a'] == 7\n"
            "def test_diamond_counts_once():\n"
            "    deps = {'app': ['l1', 'l2'], 'l1': ['core'], 'l2': ['core'], 'core': []}\n"
            "    w = {'app': 1, 'l1': 2, 'l2': 3, 'core': 10}\n"
            "    # core (10) must be counted ONCE: 1+2+3+10 = 16, not 26\n"
            "    assert total_cost(deps, w)['app'] == 16\n"
            "def test_leaf():\n"
            "    deps = {'x': []}\n"
            "    assert total_cost(deps, {'x': 5})['x'] == 5\n"
        ),
    },
]
