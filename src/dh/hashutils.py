class ChkSUM:
    from hashlib import sha256, sha512

    def __init__(self):
        self._algorithms = {}
        try:
            dummy = sha256()
            self._algorithms["sha256"] = self._hashlib_sha256
        except NameError:
            self._algorithms["sha256"] = self._openssl_sha256
        try:
            dummy = sha512()
            self._algorithms["sha512"] = self._hashlib_sha512
        except NameError:
            self._algorithms["sha512"] = self._openssl_sha512

    def _hashlib(self, algorithm, filename):
        try:
            with open(filename, "rb") as filep:
                for chunk in iter(lambda: filep.read(32768), b""):
                    algorithm.update(chunk)
            return algorithm.hexdigest()
        except OSError:
            return ""

    def _hashlib_sha256(self, filename):
        return self._hashlib(sha256(), filename)

    def _hashlib_sha512(self, filename):
        return self._hashlib(sha512(), filename)

    def _openssl(self, algorithm, filename):
        from re import match as re_match
        from subprocess import get_output

        cmd = ["openssl", "dgst", "-hex", "-r", algorithm, filename]
        output = get_output(cmd)
        if output is None:
            return ""
        matchz = re_match("^(\\\\S+) ", output)
        if matchz:
            return matchz.group(1)
        return ""

    def _openssl_sha256(self, filename):
        return self._openssl("-sha256", filename)

    def _openssl_sha512(self, filename):
        return self._openssl("-sha512", filename)

    def sha256(self, filename):
        return self._algorithms["sha256"](filename)

    def sha512(self, filename):
        return self._algorithms["sha512"](filename)

    def hash(self, filename, algorithm):
        if algorithm in self._algorithms:
            return self._algorithms[algorithm](filename)
        return ""
