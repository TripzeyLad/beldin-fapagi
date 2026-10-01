from pathlib import Path
import sys

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")

repls = [
(
"        search_paths = []\n        discovered_paths = []\n        read_required = False\n        search_refusals = 0\n",
"        search_paths = []\n        discovered_paths = []\n        read_required = False\n        search_refusals = 0\n"
"        zero_result_queries = set()\n        dead_query_repeats = 0\n"
),
(
"            if action.get('tool')=='search':\n                search_streak += 1\n                research['searches'] += 1\n\n"
"            if action.get('tool')=='search' and read_required:",
"            if action.get('tool')=='search':\n                search_streak += 1\n                research['searches'] += 1\n"
"                query_norm=str(action.get('args',{}).get('query','') if isinstance(action.get('args'),dict) else '').strip().casefold()\n"
"            else:\n                query_norm=None\n\n"
"            if query_norm and query_norm in zero_result_queries:\n"
"                dead_query_repeats += 1\n"
"                result={'error':'search_repeats_zero_result_query','executed':False,\n"
"                        'message':'That exact search already returned no matches earlier in this task. Repeating it will not find anything new. Try a different literal substring, or read/edit/test/finish instead.'}\n"
"                self.event(t,'tool_error',step=step+1,tool='search',error='search_repeats_zero_result_query')\n"
"                if dead_query_repeats >= 2:\n"
"                    self.event(t,'tool_error',step=step+1,tool='search',error='model_stuck_dead_query')\n"
"                    raise CodingError('model_stuck_dead_query')\n"
"            elif action.get('tool')=='search' and read_required:"
),
(
"                if matches:\n                    zero_search_streak = 0\n                    zero_search_intervened = False\n                else:\n                    zero_search_streak += 1",
"                if matches:\n                    zero_search_streak = 0\n                    zero_search_intervened = False\n                else:\n                    if query_norm: zero_result_queries.add(query_norm)\n                    zero_search_streak += 1"
),
]

for i, (old, new) in enumerate(repls, 1):
    count = s.count(old)
    if count != 1:
        raise SystemExit(f"REFUSING PATCH: replacement {i} expected once, found {count}")
    s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
print("DEAD_QUERY_PATCH_APPLIED")
