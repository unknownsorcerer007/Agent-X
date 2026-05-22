class ConsistentFingerprint:
    """
    A fingerprint that's consistent across ALL detection vectors.
    Sites cross-check: if WebGL says Intel but canvas says NVIDIA → bot.
    This ensures everything matches a real hardware combination.
    """

    # Hardware profile (real combinations from telemetry data)
    HARDWARE_PROFILES = [
        {
            "name": "Intel UHD 630 + i7-10700",
            "webgl_vendor": "Google Inc. (Intel)",
            "webgl_renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "cores": 8,
            "memory": 16,
            "screen_res": (1920, 1080),
            "pixel_ratio": 1.0,
        },
        {
            "name": "Intel Iris Xe + i7-1165G7",
            "webgl_vendor": "Google Inc. (Intel)",
            "webgl_renderer": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "cores": 8,
            "memory": 16,
            "screen_res": (1920, 1080),
            "pixel_ratio": 1.0,
        },
        {
            "name": "NVIDIA GTX 1660 + Ryzen 5",
            "webgl_vendor": "Google Inc. (NVIDIA)",
            "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "cores": 6,
            "memory": 16,
            "screen_res": (1920, 1080),
            "pixel_ratio": 1.0,
        },
        {
            "name": "NVIDIA RTX 3060 + i5-12400",
            "webgl_vendor": "Google Inc. (NVIDIA)",
            "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "cores": 6,
            "memory": 32,
            "screen_res": (2560, 1440),
            "pixel_ratio": 1.0,
        },
        {
            "name": "AMD Radeon RX 580 + Ryzen 7",
            "webgl_vendor": "Google Inc. (AMD)",
            "webgl_renderer": "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "cores": 8,
            "memory": 16,
            "screen_res": (1920, 1080),
            "pixel_ratio": 1.0,
        },
        {
            "name": "Apple M1 Pro",
            "webgl_vendor": "Google Inc. (Apple)",
            "webgl_renderer": "ANGLE (Apple, Apple M1 Pro, OpenGL 4.1)",
            "cores": 10,
            "memory": 16,
            "screen_res": (2560, 1600),
            "pixel_ratio": 2.0,
        },
        {
            "name": "Apple M2",
            "webgl_vendor": "Google Inc. (Apple)",
            "webgl_renderer": "ANGLE (Apple, Apple M2, OpenGL 4.1)",
            "cores": 8,
            "memory": 8,
            "screen_res": (2560, 1600),
            "pixel_ratio": 2.0,
        },
    ]

    CHROME_VERSIONS = [
        ("146", 30), ("145", 25), ("144", 20), ("143", 15),
        ("136", 5), ("133", 3), ("131", 2),
    ]

    TIMEZONES = [
        ("America/New_York", 20), ("America/Chicago", 10),
        ("America/Los_Angeles", 15), ("Europe/London", 12),
        ("Europe/Berlin", 10), ("Europe/Paris", 8),
    ]

    def __init__(self, seed: int = None):
        """Generate a consistent fingerprint from a seed."""
        if seed is None:
            seed = random.randint(1, 2**31 - 1)

        self.seed = seed
        self._rng = random.Random(seed)

        # Select hardware profile
        self.hardware = self._rng.choice(self.HARDWARE_PROFILES)

        # Select Chrome version
        versions, weights = zip(*self.CHROME_VERSIONS)
        self.chrome_version = self._weighted_choice(versions, weights)

        # Select timezone
        timezones, tz_weights = zip(*self.TIMEZONES)
        self.timezone = self._weighted_choice(timezones, tz_weights)

        # Derived values
        self.platform = "Win32" if "Apple" not in self.hardware["name"] else "MacIntel"
        self.os = "windows" if self.platform == "Win32" else "mac"

        # Canvas/Audio noise seeds (deterministic from main seed)
        self.canvas_seed = self._rng.randint(1, 2**31 - 1)
        self.audio_seed = self._rng.randint(1, 2**31 - 1)

        # Fingerprint ID (for tracking)
        self.fp_id = hashlib.md5(
            f"{seed}{self.hardware['name']}{self.chrome_version}".encode()
        ).hexdigest()[:12]

        # Build user agent
        if self.os == "windows":
            ua_os = "Windows NT 10.0; Win64; x64"
        else:
            ua_os = "Macintosh; Intel Mac OS X 10_15_7"

        self.user_agent = (
            f"Mozilla/5.0 ({ua_os}) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{self.chrome_version}.0.0.0 Safari/537.36"
        )

    def _weighted_choice(self, items, weights):
        total = sum(weights)
        r = self._rng.uniform(0, total)
        cumulative = 0
        for item, weight in zip(items, weights):
            cumulative += weight
            if r <= cumulative:
                return item
        return items[-1]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fp_id": self.fp_id,
            "seed": self.seed,
            "chrome_version": self.chrome_version,
            "platform": self.platform,
            "os": self.os,
            "user_agent": self.user_agent,
            "timezone": self.timezone,
            "webgl_vendor": self.hardware["webgl_vendor"],
            "webgl_renderer": self.hardware["webgl_renderer"],
            "hardware_concurrency": self.hardware["cores"],
            "device_memory": self.hardware["memory"],
            "screen_width": self.hardware["screen_res"][0],
            "screen_height": self.hardware["screen_res"][1],
            "pixel_ratio": self.hardware["pixel_ratio"],
            "canvas_seed": self.canvas_seed,
            "audio_seed": self.audio_seed,
        }


