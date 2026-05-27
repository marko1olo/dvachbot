from __future__ import annotations


AUDIO_EFFECT_FILTERS: dict[str, str] = {
    "anon": "asetrate=44100*0.8,atempo=1.25,firequalizer=gain=-20:f=1000,aresample=48000",
    "demon": "asetrate=44100*0.6,atempo=1.66,lowpass=3000,aresample=48000",
    "chipmunk": "asetrate=44100*1.5,atempo=0.66,aresample=48000",
    "robot": "asetrate=11025,atempo=4.0,aresample=48000",
    "echo": "aecho=0.8:0.9:1000:0.3,aresample=48000",
    "loli": "asetrate=44100*1.25,atempo=0.8,aresample=48000",
    "chad": "asetrate=44100*0.75,atempo=1.33,firequalizer=gain=10:f=80,aresample=48000",
    "trim": "silenceremove=stop_periods=-1:stop_duration=1:stop_threshold=-50dB,aresample=48000",
}


def get_audio_filter(effect: str) -> str | None:
    return AUDIO_EFFECT_FILTERS.get(effect)
