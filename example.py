"""Sample module with a few intentional issues for the AI reviewer to catch."""


def calculate_factorial(n):
    # No guard against negative n -> infinite recursion / RecursionError.
    # Recursive form also hits Python's recursion limit for large n.
    if n == 0:
        return 1
    else:
        return n * calculate_factorial(n - 1)


def average(numbers):
    # Divides by zero if the list is empty.
    total = 0
    for x in numbers:
        total += x
    return total / len(numbers)


def find_user(users, target_id):
    # Returns None implicitly if not found; caller has no way to distinguish.
    for u in users:
        if u["id"] == target_id:
            return u


if __name__ == "__main__":
    print(calculate_factorial(5))
    print(average([1, 2, 3, 4]))
