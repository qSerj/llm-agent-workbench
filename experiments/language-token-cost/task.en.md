# Fix integer range collapsing

The `ranges.py` file contains a `collapse_ranges(values)` function. Fix it so
that it follows the complete contract below.

1. The function accepts any iterable of integers and returns a string.
2. Numbers are sorted in ascending order and duplicates are removed. The input is not mutated.
3. Three or more consecutive numbers are written as `start-end`.
4. One or two consecutive numbers are written separately.
5. Fragments are separated by commas without spaces.
6. Negative boundaries keep their sign: `[-3, -2, -1]` becomes `-3--1`.
7. Empty input produces an empty string.
8. A `bool` or any value that is not an `int` raises `TypeError`.

Examples:

```python
collapse_ranges([1, 2, 3, 5, 7, 8]) == "1-3,5,7,8"
collapse_ranges(iter([4, 3, 3, 2])) == "2-4"
```

Do not add external dependencies. Check the behavior with Python commands. Edit
only `ranges.py` and do not create other files. The result must be a working
implementation, not a description of a solution.
