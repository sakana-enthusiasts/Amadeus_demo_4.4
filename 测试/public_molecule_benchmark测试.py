import random
from benchmark工具.public_molecule_benchmark import pareto_depth


def naive_depth(values):
    remaining = set(range(len(values)))
    result = [0] * len(values)
    depth = 1
    while remaining:
        front = [i for i in remaining if not any(
            all(a <= b for a, b in zip(values[j], values[i]))
            and any(a < b for a, b in zip(values[j], values[i]))
            for j in remaining if j != i)]
        for i in front:
            result[i] = depth
        remaining.difference_update(front)
        depth += 1
    return result


def test_pareto_depth_against_independent_definition():
    rng = random.Random(9126)
    for _ in range(50):
        values = [(rng.randint(-6, 6), rng.randint(-6, 6)) for i in range(50)]
        assert pareto_depth(values) == naive_depth(values)


def test_equal_vectors_and_tradeoffs():
    assert pareto_depth([(1, 1), (1, 1), (2, 2), (0, 3)]) == [1, 1, 2, 1]
    assert pareto_depth([]) == []
