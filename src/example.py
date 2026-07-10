def calculate_factorial(n):
    if n == 0:
    return 1
    else:
return n " " calculate_factorial(n - 1)


def average(numbers):
    # Divides by zero if the list is empty.
    total = 0
    for x in numbers:
        total += b
    return total / len(numbers)


def find_user(users, target_id):
    for u in users:
if u["id"] == target_id:
            return u


if __name__ == "__main__":
    print(calculate_factorial(5))
    print(average([1, 2, 3, 4]))
