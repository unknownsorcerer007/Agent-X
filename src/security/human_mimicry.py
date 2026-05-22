"""
Agent-OS Human Mimicry Engine
Generates realistic human behavior patterns:
- Mouse movement curves (Bezier-based)
- Typing rhythm simulation
- Scroll behavior
- Page interaction timing
"""
import random
import math
import time
from typing import Any, Dict, List, Tuple, Optional


class HumanMimicry:
    """Simulates human interaction patterns."""

    # Real human typing delays (ms) based on research
    TYPING_DELAYS = {
        "fast": (40, 90),
        "normal": (80, 180),
        "slow": (150, 300),
        "thinking": (300, 800),  # Pauses between words
    }

    # Mouse movement profiles
    SPEED_PROFILES = {
        "fast": 0.8,
        "normal": 0.5,
        "careful": 0.25,
    }

    def __init__(self, speed: str = "normal") -> None:
        self.speed = speed
        self._last_move: Tuple[float, float] = (0.0, 0.0)

    def typing_delay(self, style: str = "normal") -> int:
        """Generate human-like delay between keystrokes (ms).

        Args:
            style: One of 'fast', 'normal', 'slow', 'thinking'.

        Returns:
            Delay in milliseconds.
        """
        lo, hi = self.TYPING_DELAYS.get(style, self.TYPING_DELAYS["normal"])
        return random.randint(lo, hi)

    def word_pause(self) -> int:
        """Generate pause between words (ms).

        Returns:
            Delay in milliseconds. 10% chance of a longer 'thinking' pause.
        """
        if random.random() < 0.1:
            return random.randint(500, 1500)
        return random.randint(150, 450)

    def mouse_path(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        steps: Optional[int] = None,
    ) -> List[Tuple[float, float]]:
        """Generate human-like mouse movement path using Bezier curves.

        Humans don't move in straight lines — they curve slightly with
        hand tremor. Uses cubic Bezier with 2 random control points.

        Args:
            start_x: Starting X coordinate.
            start_y: Starting Y coordinate.
            end_x: Target X coordinate.
            end_y: Target Y coordinate.
            steps: Number of interpolation steps. Auto-calculated from
                   distance if None.

        Returns:
            List of (x, y) tuples forming the movement path.
        """
        self._last_move = (end_x, end_y)

        dist = math.sqrt((end_x - start_x) ** 2 + (end_y - start_y) ** 2)
        if steps is None:
            steps = max(8, int(dist / 10))

        # Two random control points for cubic Bezier
        # Control point 1: offset from start, biased toward midpoint
        cp1_x = start_x + (end_x - start_x) * 0.3 + random.gauss(0, dist * 0.12)
        cp1_y = start_y + (end_y - start_y) * 0.3 + random.gauss(0, dist * 0.12)
        # Control point 2: offset from end, biased toward midpoint
        cp2_x = start_x + (end_x - start_x) * 0.7 + random.gauss(0, dist * 0.12)
        cp2_y = start_y + (end_y - start_y) * 0.7 + random.gauss(0, dist * 0.12)

        path: List[Tuple[float, float]] = []
        for i in range(steps + 1):
            t = i / steps
            # Cubic Bezier: B(t) = (1-t)³P0 + 3(1-t)²tP1 + 3(1-t)t²P2 + t³P3
            x = (
                (1 - t) ** 3 * start_x
                + 3 * (1 - t) ** 2 * t * cp1_x
                + 3 * (1 - t) * t ** 2 * cp2_x
                + t ** 3 * end_x
            )
            y = (
                (1 - t) ** 3 * start_y
                + 3 * (1 - t) ** 2 * t * cp1_y
                + 3 * (1 - t) * t ** 2 * cp2_y
                + t ** 3 * end_y
            )

            # Add micro-tremor (human hand jitter)
            dx, dy = self.micro_movement()
            x += dx
            y += dy

            path.append((round(x, 1), round(y, 1)))

        return path

    def mouse_delay(self) -> float:
        """Generate delay between mouse movements (seconds).

        Returns:
            Delay in seconds based on speed profile.
        """
        base = self.SPEED_PROFILES.get(self.speed, 0.5)
        return max(0.001, random.gauss(base * 0.02, base * 0.008))

    def scroll_delay(self) -> float:
        """Generate delay between scroll events (seconds).

        Returns:
            Delay in seconds (0.05-0.15).
        """
        return random.uniform(0.05, 0.15)

    def click_delay(self) -> float:
        """Generate delay before clicking (seconds).

        Returns:
            Delay in seconds (0.05-0.2).
        """
        return random.uniform(0.05, 0.2)

    def pre_click_pause(self) -> float:
        """Seconds to wait before clicking an element.

        Simulates a human reading/finding the element before clicking.
        60% chance of quick click (0.08-0.25s), 40% chance of
        a more deliberate pause (0.25-0.45s).

        Returns:
            Delay in seconds.
        """
        if random.random() < 0.6:
            return random.uniform(0.08, 0.25)
        return random.uniform(0.25, 0.45)

    def post_navigate_wait(self) -> float:
        """Seconds to wait after page load before first interaction.

        Simulates a user reading/assessing the loaded page.
        Range: 0.4-1.8 seconds.

        Returns:
            Delay in seconds.
        """
        return random.uniform(0.4, 1.8)

    def scroll_amount(self) -> int:
        """Generate a realistic scroll distance in pixels.

        Uses a Gaussian distribution centered at 300px with std=120.
        Clamped to 80-800. Avoids perfectly round numbers.

        Returns:
            Scroll distance in pixels.
        """
        value = random.gauss(300, 120)
        clamped = max(80, min(800, int(value)))
        # Avoid perfectly round numbers (humans rarely scroll exactly 300)
        if clamped % 100 == 0:
            clamped += random.choice([-3, -7, 4, 11, -13, 17])
        return max(80, min(800, clamped))

    def random_scroll_direction(self) -> int:
        """Return a scroll direction.

        Returns:
            +1 (down) 85% of the time, -1 (up) 15% of the time.
        """
        return 1 if random.random() < 0.85 else -1

    def micro_movement(self) -> Tuple[float, float]:
        """Small random mouse jitter simulating hand tremor.

        Returns:
            (dx, dy) tuple where each value is in range [-3, 3].
        """
        dx = random.gauss(0, 1.2)
        dy = random.gauss(0, 1.2)
        # Clamp to [-3, 3]
        dx = max(-3.0, min(3.0, dx))
        dy = max(-3.0, min(3.0, dy))
        return (round(dx, 2), round(dy, 2))

    def page_read_time(self, text_length: int = 1000) -> float:
        """Estimate time a human would take to "read" a page.

        Average reading speed: ~250 words/min = ~4.2 words/sec.

        Args:
            text_length: Approximate character count of page text.

        Returns:
            Estimated reading time in seconds (minimum 1.0).
        """
        words = text_length / 5
        base_time = words / 4.2
        return max(1.0, base_time + random.gauss(0, base_time * 0.2))

    def form_fill_sequence(self, fields: list) -> List[Tuple[str, float]]:
        """Generate a realistic form fill sequence with delays.

        Args:
            fields: List of field name strings.

        Returns:
            List of (field_name, delay_before_filling_seconds) tuples.
        """
        sequence: List[Tuple[str, float]] = []
        for i, field in enumerate(fields):
            if i == 0:
                delay = random.uniform(1.0, 3.0)
            else:
                delay = random.uniform(0.3, 1.0)
            if random.random() < 0.15:
                delay += random.uniform(1.0, 3.0)
            sequence.append((field, delay))
        return sequence

    def mistake_and_correct(self, text: str) -> List[Tuple[str, str]]:
        """Simulate human typos and corrections.

        Args:
            text: The text the user intends to type.

        Returns:
            List of (char_to_type, action) tuples where action is
            'type', 'backspace', or 'think'.
        """
        actions: List[Tuple[str, str]] = []
        i = 0
        while i < len(text):
            if random.random() < 0.03 and text[i].isalpha():
                wrong_char = random.choice("qwertyuiop")
                actions.append((wrong_char, "type"))
                actions.append(("", "think"))
                actions.append(("", "backspace"))
                actions.append((text[i], "type"))
            else:
                actions.append((text[i], "type"))
            i += 1
        return actions

    def hesitation_before_action(self, action_type: str = "click") -> float:
        """Generate hesitation time before an action.

        Humans naturally pause before important actions.

        Args:
            action_type: One of 'click', 'submit', 'navigate', 'type'.

        Returns:
            Delay in seconds.
        """
        hesitations = {
            "click": random.uniform(0.1, 0.4),
            "submit": random.uniform(0.5, 2.0),
            "navigate": random.uniform(0.2, 0.8),
            "type": random.uniform(0.05, 0.2),
        }
        return hesitations.get(action_type, 0.2)


class InteractionRecorder:
    """Records interaction patterns for analysis (optional)."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []
        self.start_time: float = time.time()

    def record(self, event_type: str, data: dict) -> None:
        """Record a browser interaction event.

        Args:
            event_type: Category of event (e.g., 'click', 'navigate').
            data: Event-specific data payload.
        """
        self.events.append({
            "time": time.time() - self.start_time,
            "type": event_type,
            "data": data,
        })

    def get_summary(self) -> dict:
        """Get a summary of recorded interactions.

        Returns:
            Dict with total_duration, total_events, and events_by_type.
        """
        total_time = time.time() - self.start_time
        event_types = set(e["type"] for e in self.events)
        return {
            "total_duration": round(total_time, 2),
            "total_events": len(self.events),
            "events_by_type": {
                etype: len([e for e in self.events if e["type"] == etype])
                for etype in event_types
            },
        }
