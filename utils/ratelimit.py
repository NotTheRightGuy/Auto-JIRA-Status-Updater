class RateLimitHandler:
    def __init__(self):
        self.attempt_count = 0

    def get_delay(self):
        if self.attempt_count == 0:
            return 0
        return min(2**self.attempt_count, 60)  # Cap delay at 60 seconds

    def increment_attempts(self):
        self.attempt_count += 1

    def reset_attempts(self):
        self.attempt_count = 0
