# -*- coding: utf-8 -*-
import io
import struct
import sys

ZSTD_MAGIC = 0xFD2FB528
SKIP_LO = 0x184D2A50
SKIP_HI = 0x184D2A5F
DICT_MAGIC = 0xEC30A437


class ZstdError(Exception):
    pass


LL_BASE = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
           16, 18, 20, 22, 24, 28, 32, 40, 48, 64, 128, 256, 512,
           1024, 2048, 4096, 8192, 16384, 32768, 65536]
LL_BITS = [0] * 16 + [1, 1, 1, 1, 2, 2, 3, 3, 4, 6, 7, 8, 9, 10, 11, 12,
                      13, 14, 15, 16]
ML_BASE = list(range(3, 35)) + [35, 37, 39, 41, 43, 47, 51, 59, 67, 83, 99,
                                131, 259, 515, 1027, 2051, 4099, 8195,
                                16387, 32771, 65539]
ML_BITS = [0] * 32 + [1, 1, 1, 1, 2, 2, 3, 3, 4, 4, 5, 7, 8, 9, 10, 11,
                      12, 13, 14, 15, 16]

LL_DEFAULT = [4, 3, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1, 1, 1, 2, 2, 2, 2,
              2, 2, 2, 2, 2, 3, 2, 1, 1, 1, 1, 1, -1, -1, -1, -1]
ML_DEFAULT = [1, 4, 3, 2, 2, 2, 2, 2, 2] + [1] * 37 + [-1] * 7
OF_DEFAULT = [1, 1, 1, 1, 1, 1, 2, 2, 2] + [1] * 15 + [-1] * 5

_LIMITS = {0: (35, 9), 1: (31, 8), 2: (52, 9)}
_DEFAULTS = {0: (LL_DEFAULT, 6), 1: (OF_DEFAULT, 5), 2: (ML_DEFAULT, 6)}


class _BitReader(object):
    __slots__ = ('buf', 'pos', 'bit')

    def __init__(self, buf, pos=0):
        self.buf = buf
        self.pos = pos
        self.bit = 0

    def read(self, n):
        if n == 0:
            return 0
        v = 0
        got = 0
        while got < n:
            if self.pos >= len(self.buf):
                raise ZstdError("bit reader overflow")
            byte = self.buf[self.pos]
            avail = 8 - self.bit
            take = avail if avail < (n - got) else (n - got)
            chunk = (byte >> self.bit) & ((1 << take) - 1)
            v |= chunk << got
            got += take
            self.bit += take
            if self.bit == 8:
                self.bit = 0
                self.pos += 1
        return v

    def bytes_used(self):
        return self.pos + (1 if self.bit else 0)


def _read_ncount(buf, pos, max_sym, max_log):
    br = _BitReader(buf, pos)
    al = br.read(4) + 5
    if al > max_log:
        raise ZstdError("FSE accuracy log too large")
    remaining = (1 << al) + 1
    threshold = 1 << al
    nbits = al + 1
    norm = []
    prev0 = False
    while remaining > 1:
        if prev0:
            while True:
                r = br.read(2)
                if r:
                    norm.extend([0] * r)
                if r != 3:
                    break
            if len(norm) > max_sym + 1:
                raise ZstdError("FSE too many symbols")
        mx = (2 * threshold - 1) - remaining
        low = br.read(nbits - 1)
        if low < mx:
            count = low
        else:
            if br.read(1):
                count = low + threshold
            else:
                count = low
            if count >= threshold:
                count -= mx
        count -= 1
        remaining -= count if count >= 0 else 1
        if remaining < 1:
            raise ZstdError("FSE invalid counts")
        norm.append(count)
        if len(norm) > max_sym + 1:
            raise ZstdError("FSE too many symbols")
        prev0 = (count == 0)
        while remaining < threshold:
            nbits -= 1
            threshold >>= 1
    if remaining != 1:
        raise ZstdError("FSE header corrupt")
    return norm, al, br.bytes_used() - pos


def _build_fse(norm, al):
    size = 1 << al
    sym = [0] * size
    nxt = [0] * len(norm)
    high = size - 1
    for s, c in enumerate(norm):
        if c == -1:
            sym[high] = s
            high -= 1
            nxt[s] = 1
        else:
            nxt[s] = c
    step = (size >> 1) + (size >> 3) + 3
    mask = size - 1
    pos = 0
    for s, c in enumerate(norm):
        for _ in range(c if c > 0 else 0):
            sym[pos] = s
            pos = (pos + step) & mask
            while pos > high:
                pos = (pos + step) & mask
    if pos != 0:
        raise ZstdError("FSE table spread failed")
    nb = [0] * size
    base = [0] * size
    for u in range(size):
        s = sym[u]
        ns = nxt[s]
        nxt[s] = ns + 1
        b = al - (ns.bit_length() - 1)
        nb[u] = b
        base[u] = (ns << b) - size
    return sym, nb, base


def _seq_table(sym, nb, base, log, kind):
    try:
        if kind == 0:
            vb = [LL_BASE[s] for s in sym]
            vbits = [LL_BITS[s] for s in sym]
        elif kind == 2:
            vb = [ML_BASE[s] for s in sym]
            vbits = [ML_BITS[s] for s in sym]
        else:
            if max(sym) > 31:
                raise ZstdError("offset code too large")
            vb = [1 << s for s in sym]
            vbits = list(sym)
    except IndexError:
        raise ZstdError("symbol code out of range")
    return (log, sym, nb, base, vb, vbits)


_PREDEF = {}


def _predefined(kind):
    t = _PREDEF.get(kind)
    if t is None:
        norm, al = _DEFAULTS[kind]
        sym, nb, base = _build_fse(norm, al)
        t = _seq_table(sym, nb, base, al, kind)
        _PREDEF[kind] = t
    return t


def _read_seq_table(kind, mode, buf, pos, prev):
    if mode == 0:
        return _predefined(kind), pos
    if mode == 1:
        return _seq_table([buf[pos]], [0], [0], 0, kind), pos + 1
    if mode == 2:
        max_sym, max_log = _LIMITS[kind]
        norm, al, used = _read_ncount(buf, pos, max_sym, max_log)
        sym, nb, base = _build_fse(norm, al)
        return _seq_table(sym, nb, base, al, kind), pos + used
    if prev is None:
        raise ZstdError("repeat mode without previous table")
    return prev, pos


def _read_huf_tree(buf, pos):
    hb = buf[pos]
    pos += 1
    if hb >= 128:
        n = hb - 127
        nbytes = (n + 1) >> 1
        data = buf[pos:pos + nbytes]
        if len(data) != nbytes:
            raise ZstdError("Huffman weights truncated")
        weights = []
        for b in data:
            weights.append(b >> 4)
            weights.append(b & 15)
        del weights[n:]
        pos += nbytes
    else:
        data = buf[pos:pos + hb]
        if hb == 0 or len(data) != hb:
            raise ZstdError("Huffman FSE weights truncated")
        norm, al, used = _read_ncount(data, 0, 255, 6)
        sym, nb, base = _build_fse(norm, al)
        stream = data[used:]
        if not stream or stream[-1] == 0:
            raise ZstdError("Huffman weights stream corrupt")
        last = stream[-1]
        bits_in_last = last.bit_length()
        total_bits = (len(stream) - 1) * 8 + bits_in_last - 1
        if total_bits < 2 * al:
            raise ZstdError("Huffman weights stream too short")
        pos_bits = total_bits - al
        packed = int.from_bytes(stream[:-1], 'little') | (last << ((len(stream) - 1) * 8))
        s1 = (packed >> pos_bits) & ((1 << al) - 1)
        pos_bits -= al
        s2 = (packed >> pos_bits) & ((1 << al) - 1)
        weights = []
        toggle = 0
        while True:
            if toggle == 0:
                weights.append(sym[s1])
                b = nb[s1]
                if b > pos_bits:
                    weights.append(sym[s2])
                    break
                pos_bits -= b
                s1 = base[s1] + ((packed >> pos_bits) & ((1 << b) - 1))
            else:
                weights.append(sym[s2])
                b = nb[s2]
                if b > pos_bits:
                    weights.append(sym[s1])
                    break
                pos_bits -= b
                s2 = base[s2] + ((packed >> pos_bits) & ((1 << b) - 1))
            toggle ^= 1
            if len(weights) > 255:
                raise ZstdError("too many Huffman weights")
        if len(weights) > 255:
            raise ZstdError("too many Huffman weights")
        pos += hb

    total = 0
    for w in weights:
        if w > 12:
            raise ZstdError("Huffman weight too large")
        if w:
            total += 1 << (w - 1)
    if total == 0:
        raise ZstdError("Huffman: no symbols")
    mb = total.bit_length()
    if mb > 12:
        raise ZstdError("Huffman: too many bits")
    left = (1 << mb) - total
    if left & (left - 1):
        raise ZstdError("Huffman: weights do not sum to power of 2")
    if left == 0:
        raise ZstdError("Huffman: no leftover for max symbol")
    weights.append(left.bit_length())

    size = 1 << mb
    tsym = [0] * size
    tnb = [0] * size
    idx = 0
    for w in range(1, mb + 1):
        cnt = 1 << (w - 1)
        nbits = mb + 1 - w
        for s, ws in enumerate(weights):
            if ws == w:
                tsym[idx:idx + cnt] = [s] * cnt
                tnb[idx:idx + cnt] = [nbits] * cnt
                idx += cnt
    if idx != size:
        raise ZstdError("Huffman table incomplete")
    return tsym, tnb, mb, pos


def _huf_stream(buf, tsym, tnb, mb, count):
    res = bytearray(count)
    if count == 0:
        return bytes(res)
    if not buf or buf[-1] == 0:
        raise ZstdError("Huffman stream corrupt")
    last = buf[-1]
    cnt = last.bit_length() - 1
    acc = last & ((1 << cnt) - 1)
    ptr = len(buf) - 2
    mask = (1 << mb) - 1
    for i in range(count):
        while cnt < mb:
            if ptr < 0:
                acc <<= (mb - cnt)
                cnt = mb
                break
            acc = (acc << 8) | buf[ptr]
            cnt += 8
            ptr -= 1
        shift = cnt - mb
        idx = (acc >> shift) & mask
        res[i] = tsym[idx]
        cnt -= tnb[idx]
        if cnt < 64:
            acc &= (1 << cnt) - 1
    return bytes(res)


class _State(object):
    __slots__ = ('huf', 'tabs', 'rep')

    def __init__(self):
        self.huf = None
        self.tabs = [None, None, None]
        self.rep = (1, 4, 8)


def _parse_literals(block, st):
    b0 = block[0]
    typ = b0 & 3
    sf = (b0 >> 2) & 3
    if typ < 2:
        if sf == 0 or sf == 2:
            hdr = 1
            regen = b0 >> 3
        elif sf == 1:
            hdr = 2
            regen = (b0 | (block[1] << 8)) >> 4
        else:
            hdr = 3
            regen = (b0 | (block[1] << 8) | (block[2] << 16)) >> 4
        if typ == 0:
            end = hdr + regen
            if end > len(block):
                raise ZstdError("raw literals truncated")
            return block[hdr:end], end
        return bytes(block[hdr:hdr + 1]) * regen, hdr + 1

    if sf == 0:
        hdr, nstreams, bsz = 3, 1, 10
    elif sf == 1:
        hdr, nstreams, bsz = 3, 4, 10
    elif sf == 2:
        hdr, nstreams, bsz = 4, 4, 14
    else:
        hdr, nstreams, bsz = 5, 4, 18
    v = int.from_bytes(block[:hdr], 'little') >> 4
    m = (1 << bsz) - 1
    regen = v & m
    comp = (v >> bsz) & m
    end = hdr + comp
    if end > len(block):
        raise ZstdError("compressed literals truncated")
    pos = hdr
    if typ == 2:
        tsym, tnb, mb, pos = _read_huf_tree(block, pos)
        st.huf = (tsym, tnb, mb)
    else:
        if st.huf is None:
            raise ZstdError("treeless literals without table")
        tsym, tnb, mb = st.huf
    if pos > end:
        raise ZstdError("Huffman tree overruns literals")
    if nstreams == 1:
        lits = _huf_stream(block[pos:end], tsym, tnb, mb, regen)
    else:
        if pos + 6 > end:
            raise ZstdError("jump table truncated")
        s1 = block[pos] | (block[pos + 1] << 8)
        s2 = block[pos + 2] | (block[pos + 3] << 8)
        s3 = block[pos + 4] | (block[pos + 5] << 8)
        pos += 6
        s4 = end - pos - s1 - s2 - s3
        if s4 < 0:
            raise ZstdError("jump table invalid")
        seg = (regen + 3) >> 2
        last_n = regen - 3 * seg
        if last_n < 0:
            raise ZstdError("literals size invalid")
        lits = bytearray()
        for sz, n in ((s1, seg), (s2, seg), (s3, seg), (s4, last_n)):
            lits += _huf_stream(block[pos:pos + sz], tsym, tnb, mb, n)
            pos += sz
    return bytes(lits), end


def _run_sequences(bs, nseq, tabs, lits, out, st):
    ll_log, ll_sym, ll_nb, ll_base, ll_vb, ll_vbits = tabs[0]
    of_log, of_sym, of_nb, of_base, of_vb, of_vbits = tabs[1]
    ml_log, ml_sym, ml_nb, ml_base, ml_vb, ml_vbits = tabs[2]

    if not bs or bs[-1] == 0:
        raise ZstdError("sequence bitstream corrupt")
    last = bs[-1]
    cnt = last.bit_length() - 1
    acc = last & ((1 << cnt) - 1)
    ptr = len(bs) - 2
    pad = 0

    if ptr >= 0:
        k = ptr + 1 if ptr < 15 else 16
        acc = ((acc & ((1 << cnt) - 1)) << (8 * k)) | \
            int.from_bytes(bs[ptr - k + 1:ptr + 1], 'little')
        cnt += 8 * k
        ptr -= k
    if cnt < 96:
        acc = (acc & ((1 << cnt) - 1)) << (96 - cnt)
        pad += 96 - cnt
        cnt = 96
    cnt -= ll_log
    ll_s = (acc >> cnt) & ((1 << ll_log) - 1)
    cnt -= of_log
    of_s = (acc >> cnt) & ((1 << of_log) - 1)
    cnt -= ml_log
    ml_s = (acc >> cnt) & ((1 << ml_log) - 1)

    rep0, rep1, rep2 = st.rep
    lp = 0
    nl = len(lits)
    final = nseq - 1

    for i in range(nseq):
        if cnt < 96:
            if ptr >= 0:
                k = ptr + 1 if ptr < 15 else 16
                acc = ((acc & ((1 << cnt) - 1)) << (8 * k)) | \
                    int.from_bytes(bs[ptr - k + 1:ptr + 1], 'little')
                cnt += 8 * k
                ptr -= k
            if cnt < 96:
                acc = (acc & ((1 << cnt) - 1)) << (96 - cnt)
                pad += 96 - cnt
                cnt = 96

        b = of_vbits[of_s]
        cnt -= b
        ov = of_vb[of_s] + ((acc >> cnt) & ((1 << b) - 1))
        b = ml_vbits[ml_s]
        cnt -= b
        mlen = ml_vb[ml_s] + ((acc >> cnt) & ((1 << b) - 1))
        b = ll_vbits[ll_s]
        cnt -= b
        llen = ll_vb[ll_s] + ((acc >> cnt) & ((1 << b) - 1))

        if i != final:
            b = ll_nb[ll_s]
            cnt -= b
            ll_s = ll_base[ll_s] + ((acc >> cnt) & ((1 << b) - 1))
            b = ml_nb[ml_s]
            cnt -= b
            ml_s = ml_base[ml_s] + ((acc >> cnt) & ((1 << b) - 1))
            b = of_nb[of_s]
            cnt -= b
            of_s = of_base[of_s] + ((acc >> cnt) & ((1 << b) - 1))

        if ov > 3:
            off = ov - 3
            rep2 = rep1
            rep1 = rep0
            rep0 = off
        else:
            idx = ov - 1 + (1 if llen == 0 else 0)
            if idx == 0:
                off = rep0
            elif idx == 1:
                off = rep1
                rep1 = rep0
                rep0 = off
            elif idx == 2:
                off = rep2
                rep2 = rep1
                rep1 = rep0
                rep0 = off
            else:
                off = rep0 - 1
                rep2 = rep1
                rep1 = rep0
                rep0 = off

        if llen:
            end = lp + llen
            if end > nl:
                raise ZstdError("literals overrun")
            out += lits[lp:end]
            lp = end
        olen = len(out)
        if off <= 0 or off > olen:
            raise ZstdError("bad match offset %d" % off)
        start = olen - off
        if off >= mlen:
            out += out[start:start + mlen]
        else:
            pat = out[start:]
            q, r = divmod(mlen, off)
            out += pat * q + pat[:r]

    if cnt < pad:
        raise ZstdError("sequence bitstream overread")
    if lp < nl:
        out += lits[lp:]
    st.rep = (rep0, rep1, rep2)


def _decode_block(block, out, st):
    try:
        lits, pos = _parse_literals(block, st)
        b = block[pos]
        pos += 1
        if b == 0:
            out += lits
            return
        if b < 128:
            nseq = b
        elif b < 255:
            nseq = ((b - 128) << 8) + block[pos]
            pos += 1
        else:
            nseq = block[pos] + (block[pos + 1] << 8) + 0x7F00
            pos += 2
        modes = block[pos]
        pos += 1
        tabs = st.tabs
        new = [None, None, None]
        for kind, shift in ((0, 6), (1, 4), (2, 2)):
            new[kind], pos = _read_seq_table(
                kind, (modes >> shift) & 3, block, pos, tabs[kind])
        st.tabs = new
        _run_sequences(block[pos:], nseq, new, lits, out, st)
    except IndexError:
        raise ZstdError("corrupt block")


_M64 = (1 << 64) - 1
_P1 = 0x9E3779B185EBCA87
_P2 = 0xC2B2AE3D27D4EB4F
_P3 = 0x165667B19E3779F9
_P4 = 0x85EBCA77C2B2AE63
_P5 = 0x27D4EB2F165667C5


def _rotl(x, r):
    return ((x << r) | (x >> (64 - r))) & _M64


def _xround(acc, inp):
    acc = (acc + inp * _P2) & _M64
    return (_rotl(acc, 31) * _P1) & _M64


class XXH64(object):
    def __init__(self, seed=0):
        self.seed = seed
        self.v = [(seed + _P1 + _P2) & _M64, (seed + _P2) & _M64,
                  seed & _M64, (seed - _P1) & _M64]
        self.total = 0
        self.buf = b''

    def update(self, data):
        self.total += len(data)
        if self.buf:
            data = self.buf + bytes(data)
        n = len(data) - (len(data) & 31)
        if n:
            v1, v2, v3, v4 = self.v
            M = _M64
            P1 = _P1
            P2 = _P2
            for a, b, c, d in struct.iter_unpack('<4Q', memoryview(data)[:n]):
                v1 = (v1 + a * P2) & M
                v1 = ((((v1 << 31) | (v1 >> 33)) & M) * P1) & M
                v2 = (v2 + b * P2) & M
                v2 = ((((v2 << 31) | (v2 >> 33)) & M) * P1) & M
                v3 = (v3 + c * P2) & M
                v3 = ((((v3 << 31) | (v3 >> 33)) & M) * P1) & M
                v4 = (v4 + d * P2) & M
                v4 = ((((v4 << 31) | (v4 >> 33)) & M) * P1) & M
            self.v = [v1, v2, v3, v4]
        self.buf = bytes(data[n:])

    def digest(self):
        v1, v2, v3, v4 = self.v
        if self.total >= 32:
            h = (_rotl(v1, 1) + _rotl(v2, 7) + _rotl(v3, 12) + _rotl(v4, 18)) & _M64
            for v in (v1, v2, v3, v4):
                h ^= _xround(0, v)
                h = (h * _P1 + _P4) & _M64
        else:
            h = (self.seed + _P5) & _M64
        h = (h + self.total) & _M64
        p = self.buf
        i = 0
        n = len(p)
        while i + 8 <= n:
            k = int.from_bytes(p[i:i + 8], 'little')
            h ^= _xround(0, k)
            h = (_rotl(h, 27) * _P1 + _P4) & _M64
            i += 8
        if i + 4 <= n:
            h ^= (int.from_bytes(p[i:i + 4], 'little') * _P1) & _M64
            h = (_rotl(h, 23) * _P2 + _P3) & _M64
            i += 4
        while i < n:
            h ^= (p[i] * _P5) & _M64
            h = (_rotl(h, 11) * _P1) & _M64
            i += 1
        h ^= h >> 33
        h = (h * _P2) & _M64
        h ^= h >> 29
        h = (h * _P3) & _M64
        h ^= h >> 32
        return h


class _Dict(object):
    __slots__ = ('id', 'content', 'huf', 'tabs', 'rep')


def _parse_dict(data):
    data = bytes(data)
    d = _Dict()
    if len(data) >= 8 and int.from_bytes(data[:4], 'little') == DICT_MAGIC:
        d.id = int.from_bytes(data[4:8], 'little')
        try:
            tsym, tnb, mb, pos = _read_huf_tree(data, 8)
            d.huf = (tsym, tnb, mb)
            tabs = [None, None, None]
            for kind in (1, 2, 0):
                max_sym, max_log = _LIMITS[kind]
                norm, al, used = _read_ncount(data, pos, max_sym, max_log)
                sym, nb, base = _build_fse(norm, al)
                tabs[kind] = _seq_table(sym, nb, base, al, kind)
                pos += used
            if pos + 12 > len(data):
                raise ZstdError("dictionary truncated")
            rep = tuple(int.from_bytes(data[pos + 4 * i:pos + 4 * i + 4], 'little')
                        for i in range(3))
            pos += 12
        except IndexError:
            raise ZstdError("dictionary corrupt")
        d.content = data[pos:]
        d.tabs = tabs
        for r in rep:
            if r == 0 or r > len(d.content):
                raise ZstdError("dictionary has invalid repeat offsets")
        d.rep = rep
    else:
        d.id = 0
        d.content = data
        d.huf = None
        d.tabs = [None, None, None]
        d.rep = (1, 4, 8)
    return d


def _prepare_dicts(dictionaries):
    if dictionaries is None:
        return {}, None
    if isinstance(dictionaries, (bytes, bytearray, memoryview)):
        d = _parse_dict(dictionaries)
        return {d.id: d}, d
    if isinstance(dictionaries, dict):
        items = list(dictionaries.values())
    else:
        items = list(dictionaries)
    by_id = {}
    for it in items:
        d = it if isinstance(it, _Dict) else _parse_dict(it)
        by_id[d.id] = d
    return by_id, None


def _read_exact(fin, n):
    data = fin.read(n)
    if len(data) == n:
        return data
    buf = bytearray(data)
    while len(buf) < n:
        more = fin.read(n - len(buf))
        if not more:
            raise ZstdError("unexpected end of data")
        buf += more
    return bytes(buf)


_FLUSH = 1 << 21


def iter_decompress(fin, dictionaries=None, verify_checksum=True):
    by_id, default_dict = _prepare_dicts(dictionaries)
    while True:
        m = fin.read(4)
        if not m:
            return
        if len(m) < 4:
            m += _read_exact(fin, 4 - len(m))
        magic = int.from_bytes(m, 'little')
        if SKIP_LO <= magic <= SKIP_HI:
            sz = int.from_bytes(_read_exact(fin, 4), 'little')
            _read_exact(fin, sz)
            continue
        if magic != ZSTD_MAGIC:
            raise ZstdError("bad magic 0x%08X" % magic)

        fhd = _read_exact(fin, 1)[0]
        fcs_flag = fhd >> 6
        single = (fhd >> 5) & 1
        has_ck = (fhd >> 2) & 1
        did = fhd & 3
        if fhd & 8:
            raise ZstdError("reserved bit set")
        window = 0
        if not single:
            wd = _read_exact(fin, 1)[0]
            wl = 10 + (wd >> 3)
            window = (1 << wl) + ((1 << wl) >> 3) * (wd & 7)
        dlen = (0, 1, 2, 4)[did]
        dict_id = int.from_bytes(_read_exact(fin, dlen), 'little') if dlen else 0
        flen = (1 if single else 0, 2, 4, 8)[fcs_flag]
        fcs = None
        if flen:
            fcs = int.from_bytes(_read_exact(fin, flen), 'little')
            if fcs_flag == 1:
                fcs += 256
        if single:
            window = fcs
        keep = max(window, 1 << 17)

        st = _State()
        out = bytearray()
        base = 0
        if dict_id:
            d = by_id.get(dict_id)
            if d is None:
                raise ZstdError("frame needs dictionary id %d" % dict_id)
        else:
            d = default_dict
        if d is not None:
            out += d.content
            base = len(out)
            st.huf = d.huf
            st.tabs = list(d.tabs)
            st.rep = d.rep

        hasher = XXH64() if (has_ck and verify_checksum) else None
        produced = 0
        while True:
            bh = int.from_bytes(_read_exact(fin, 3), 'little')
            last = bh & 1
            btype = (bh >> 1) & 3
            bsize = bh >> 3
            if btype == 0:
                out += _read_exact(fin, bsize)
            elif btype == 1:
                out += _read_exact(fin, 1) * bsize
            elif btype == 2:
                _decode_block(_read_exact(fin, bsize), out, st)
            else:
                raise ZstdError("reserved block type")
            if len(out) >= keep + _FLUSH:
                n = len(out) - keep
                if n > base:
                    chunk = bytes(out[base:n])
                    del out[:n]
                    base = 0
                    produced += len(chunk)
                    if hasher:
                        hasher.update(chunk)
                    yield chunk
            if last:
                break
        tail = bytes(out[base:])
        produced += len(tail)
        if hasher:
            hasher.update(tail)
        if has_ck:
            ck = _read_exact(fin, 4)
            if hasher and (hasher.digest() & 0xFFFFFFFF) != int.from_bytes(ck, 'little'):
                raise ZstdError("content checksum mismatch")
        if fcs is not None and produced != fcs:
            raise ZstdError("content size mismatch: %d != %d" % (produced, fcs))
        if tail:
            yield tail


def decompress(data, dictionaries=None, verify_checksum=True):
    return b''.join(iter_decompress(io.BytesIO(data), dictionaries, verify_checksum))


def decompress_file(src, dst, dictionaries=None, verify_checksum=True):
    total = 0
    with open(src, 'rb') as fi, open(dst, 'wb') as fo:
        for chunk in iter_decompress(fi, dictionaries, verify_checksum):
            fo.write(chunk)
            total += len(chunk)
    return total


class ZstdReader(io.RawIOBase):
    def __init__(self, fileobj, dictionaries=None, verify_checksum=True):
        io.RawIOBase.__init__(self)
        self._gen = iter_decompress(fileobj, dictionaries, verify_checksum)
        self._buf = bytearray()
        self._eof = False

    def readable(self):
        return True

    def readinto(self, b):
        n = len(b)
        while len(self._buf) < n and not self._eof:
            try:
                self._buf += next(self._gen)
            except StopIteration:
                self._eof = True
        k = min(n, len(self._buf))
        b[:k] = self._buf[:k]
        del self._buf[:k]
        return k


def is_zstd(data):
    if len(data) < 4:
        return False
    m = int.from_bytes(data[:4], 'little')
    return m == ZSTD_MAGIC or SKIP_LO <= m <= SKIP_HI


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("usage: zstd_pure_fixed.py in.zst out")
        sys.exit(1)
    print(decompress_file(sys.argv[1], sys.argv[2]), "bytes")


__all__ = ['decompress', 'decompress_file', 'iter_decompress',
           'ZstdReader', 'is_zstd', 'ZstdError', 'XXH64']
