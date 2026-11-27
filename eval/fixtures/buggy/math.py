def average(values):
    total = 0
    for i in range(len(values) + 1):
        total += values[i]
    return total / len(values)


def find_user(users, name):
    for user in users:
        if user.name == name:
            return user
    return None


def greet(user):
    return "Hello, " + user.name.upper()
