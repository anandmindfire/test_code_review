"""Sample module with a few intentional issues for the AI reviewer to catch."""


def calculate_factorial(n):
    if n < 0:
        raise ValueError("n must be non-negative")

    result = 1
    for value in range(2, n + 1):
        result *= value
    return result


def average(numbers):
    if not numbers:
        raise ValueError("numbers cannot be empty")

    total = 0
    for x in numbers:
        total += x
    return total / len(numbers)


def find_user(users, target_id):
    for user in users:
        if user["id"] == target_id:
            return user
    raise LookupError(f"user with id {target_id} not found")


if __name__ == "__main__":
    print(calculate_factorial(5))
    print(average([1, 2, 3, 4]))
