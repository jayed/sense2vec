from typing import Callable, Tuple, List, Union, Iterable
from pathlib import Path
from spacy.vectors import Vectors
from spacy.strings import StringStore
import numpy
import srsly

from .util import make_key, split_key


class Sense2Vec(object):
    def __init__(
        self,
        shape: tuple = (1000, 128),
        strings: StringStore = None,
        make_key: Callable[[str, str], str] = make_key,
        split_key: Callable[[str], Tuple[str, str]] = split_key,
        senses: List[str] = [],
    ):
        self.make_key = make_key
        self.split_key = split_key
        self.vectors = Vectors(shape=shape)
        self.strings = StringStore() if strings is None else strings
        self.cfg = {"senses": senses}

    @property
    def senses(self) -> List[str]:
        return self.cfg.get("senses", [])

    def __len__(self) -> int:
        return len(self.vectors)

    def __contains__(self, key: Union[str, int]) -> bool:
        key = key if isinstance(key, int) else self.strings[key]
        return key in self.vectors

    def __getitem__(self, key: Union[str, int]) -> numpy.ndarray:
        key = key if isinstance(key, int) else self.strings[key]
        if key in self.vectors:
            return self.vectors[key]

    def __iter__(self):
        yield from self.items()

    def add(self, key: Union[str, int], vector: numpy.ndarray):
        if not isinstance(key, int):
            key = self.strings.add(key)
        self.vectors.add(key, vector=vector)

    def items(self):
        for key, value in self.vectors.items():
            yield self.strings[key], value

    def keys(self):
        for key in self.vectors.keys():
            yield self.strings[key]

    def values(self):
        yield from self.vectors.values()

    def most_similar(
        self, keys: Iterable[str], n_similar: int = 10
    ) -> List[Tuple[str, float]]:
        if not isinstance(keys, (list, tuple)):
            raise ValueError(f"Expected iterable of keys. Got: {type(keys)}")
        vecs = [self[key] for key in keys if key in self]
        queries = numpy.asarray(vecs, dtype=numpy.float32)
        result_keys, _, scores = self.vectors.most_similar(queries)
        result = list(zip(result_keys, scores))
        result = [(self.strings[key], score) for key, score in result if key]
        result = [(key, score) for key, score in result if key not in keys]
        # TODO: handle this better?
        return result[:n_similar]

    def get_other_senses(self, key: str) -> List[str]:
        result = []
        word, orig_sense = self.split_key(key)
        for sense in self.senses:
            new_key = self.make_key(word, sense)
            if sense != orig_sense and new_key in self:
                result.append(new_key)
        return result

    def get_best_sense(self, word: str) -> Tuple[str, Union[str, None]]:
        # TODO: implement properly?
        if not self.senses:
            return (word, None)
        versions = [word, word.upper(), word.title()] if word.islower() else [word]
        freqs = []
        for text in versions:
            for sense in self.senses:
                key = self.make_key(text, sense)
                row = self.vectors.find(key=key)
                freqs.append((row, (text, sense)))
        return max(freqs)[1] if freqs else (word, None)

    def to_bytes(self, exclude: Iterable[str] = tuple()) -> bytes:
        data = {"vectors": self.vectors.to_bytes(), "cfg": self.cfg}
        if "strings" not in exclude:
            data["strings"] = self.strings.to_bytes()
        return srsly.msgpack_dumps(data)

    def from_bytes(self, bytes_data: bytes, exclude: Iterable[str] = tuple()):
        data = srsly.msgpack_loads(bytes_data)
        self.vectors = Vectors().from_bytes(data["vectors"])
        if "strings" not in exclude and "strings" in data:
            self.strings = StringStore().from_bytes(data["strings"])
        self.cfg = data["cfg"]
        return self

    def from_disk(self, path: Union[Path, str], exclude: Iterable[str] = tuple()):
        path = Path(path)
        strings_path = path / "strings.json"
        self.vectors = Vectors().from_disk(path)
        if "strings" not in exclude and strings_path.exists():
            self.strings = StringStore().from_disk(strings_path)
        self.cfg = srsly.read_json(path / "cfg")
        return self

    def to_disk(self, path: Union[Path, str], exclude: Iterable[str] = tuple()):
        path = Path(path)
        self.vectors.to_disk(path)
        if "strings" not in exclude:
            self.strings.to_disk(path / "strings.json")
        srsly.write_json(path / "cfg")
