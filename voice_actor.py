import re
import random

import torch
from omegaconf import OmegaConf
import torchaudio

""" Transform a numpy array to a PCM bytestring """
import struct
from io import BytesIO, FileIO
import wave
import numpy as np

def _make_wav(data, rate):
    try:
        data = np.array(data, dtype=float)
        if len(data.shape) == 1:
            nchan = 1
        elif len(data.shape) == 2:
            # In wave files,channels are interleaved. E.g.,
            # "L1R1L2R2..." for stereo. See
            # http://msdn.microsoft.com/en-us/library/windows/hardware/dn653308(v=vs.85).aspx
            # for channel ordering
            nchan = data.shape[0]
            data = data.T.ravel()
        else:
            raise ValueError('Array audio input must be a 1D or 2D array')
        scaled = np.int16(data/np.max(np.abs(data))*32767).tolist()
    except ImportError:
        # check that it is a "1D" list
        idata = iter(data)  # fails if not an iterable
        try:
            iter(idata.next())
            raise TypeError('Only lists of mono audio are '
                'supported if numpy is not installed')
        except TypeError:
            # this means it's not a nested list, which is what we want
            pass
        maxabsvalue = float(max([abs(x) for x in data]))
        scaled = [int(x/maxabsvalue*32767) for x in data]
        nchan = 1

    fp = BytesIO()
    waveobj = wave.open(fp,mode='wb')
    waveobj.setnchannels(nchan)
    waveobj.setframerate(rate)
    waveobj.setsampwidth(2)
    waveobj.setcomptype('NONE','NONE')
    waveobj.writeframes(b''.join([struct.pack('<h',x) for x in scaled]))
    val = fp.getvalue()
    waveobj.close()
    # fp.seek(0)
    return val

# see latest avaiable models
models = OmegaConf.load('latest_silero_models.yml')
available_languages = list(models.tts_models.keys())
# print(f'Available languages {available_languages}')

# for lang in available_languages:
#     speakers = list(models.tts_models.get(lang).keys())
#     print(f'Available speakers for {lang}: {speakers}')

def voice_act(text):
    # text = text[:140]
    # print(text)
    language = 'ru'
    # speaker = 'ruslan_16khz'
    speaker = random.choice([s for s in list(models.tts_models.get(language).keys()) if re.compile('^.*_16khz$').match(s)])
    device = torch.device('cpu')

    (model,
    symbols,
    sample_rate,
    example_text,
    apply_tts) = torch.hub.load(repo_or_dir='snakers4/silero-models',
                                            model='silero_tts',
                                            language=language,
                                            speaker=speaker)

    # torchaudio.set_audio_backend('sox_io')
    model = model.to(device)  # gpu or cpu
    # print(texts)
    audio = apply_tts(texts=text,
                    model=model,
                    sample_rate=sample_rate,
                    symbols=symbols,
                    device=device)

    # with open('output.wav', 'wb') as fp:
    #     fp.write(_make_wav(audio[0], rate = sample_rate).read())
    # wav = []
    # for audio in audios:
    #     wav.append(_make_wav(audio, rate = sample_rate))
    # return wav[-1:] + wav[:-1]
    # return _make_wav(audio[0], rate = sample_rate)
    for i, _audio in enumerate(audio):
        torchaudio.save(f'test_{str(i).zfill(2)}.wav',
                        _audio.unsqueeze(0),
                        sample_rate=16000,
                        bits_per_sample=16)
    return '0'

if __name__=='__main__':
    # wav = voice_act('Жили-были три китайца - Як, Як-Цидрак, Як-Цидрак-Цидрон-Цидрони, И еще три китаянки - Цыпа, Цыпа-Дрипа, Цыпа-Дрипа-Лампомпони. Поженились Як на Цыпе, Як-Цидрак на Цыпе-Дрипе, Як-Цидрак-Цидрон-Цидрони на Цыпе-Дрипе-Лампомпони. Вот у них родились дети: у Яка с Цыпой — Шах, у Як-Цидрака с Цыпой-Дрыпой — Шах-Шарах, у Як-Цидрак-Цидрони с Цыпо-Дрыпой-Лампопони — Шах-Шарах-Шарони.')
    # wav = voice_act('Жили-были три китайца - Як, Як-Цидрак, Як-Цидрак-Цидрон-Цидрони, И еще три китаянки - Цыпа, Цыпа-Дрипа, Цыпа-Дрипа-Лампомпони.')
    wav = voice_act('На отделанном вагонкой балконе его квартиры — целая экспозиция: российский триколор и флаг пограничных войск, над ними висят две фуражки — пограничная с советской кокардой и прокурорская, между ними — наградное холодное оружие, на многих клинках — дарственные надписи от руководителей разных ведомств, но по-настоящему теплые эмоции у Бакина вызывают только атрибуты пограничных войск: «Присягу-то я один раз давал, в армии». ')
    with open(f'output.wav', 'wb') as fp:
        fp.write(wav)
