import unittest
from common.audio_effects import get_audio_filter, AUDIO_EFFECT_FILTERS

class TestAudioEffects(unittest.TestCase):
    def test_get_existing_audio_filter(self):
        # Test for a known filter
        self.assertEqual(
            get_audio_filter("anon"),
            "asetrate=44100*0.8,atempo=1.25,firequalizer=gain=-20:f=1000,aresample=48000"
        )
        self.assertEqual(
            get_audio_filter("demon"),
            "asetrate=44100*0.6,atempo=1.66,lowpass=3000,aresample=48000"
        )

    def test_get_non_existing_audio_filter(self):
        # Test for a non-existing filter which should return None
        self.assertIsNone(get_audio_filter("non_existent_effect"))

    def test_all_keys_are_available(self):
        # Test that all keys in the dictionary can be retrieved
        for key, value in AUDIO_EFFECT_FILTERS.items():
            self.assertEqual(get_audio_filter(key), value)

if __name__ == '__main__':
    unittest.main()
