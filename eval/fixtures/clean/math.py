def average(values):
    if not values:
        return 0.0
    total = 0
    for i in range(len(values)):
        total += values[i]
    return total / len(values)


def find_user(users, name):
    for user in users:
        if user.name == name:
            return user
    return None


def greet(user):
    if user is None:
        return "Hello, guest"
    return "Hello, " + user.name.upper()
