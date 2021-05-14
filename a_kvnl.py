__all__ = (
    'DecodingError', 'EncodingError',
    'DECODERS', 'ENCODERS', 'TYPES',
    'decode_line', 'encode_line',
    'decode_block', 'encode_block',
)


from datetime import datetime


class DecodingError(Exception):
    pass


class EncodingError(Exception):
    pass


DECODERS = {
    ('Int', 'I'): lambda v: int(v),
    ('Float', 'F'): lambda v: float(v),
    ('Unicode', 'U'): lambda v: v.decode('utf-8'),
    ('ASCII', 'A'): lambda v: v.decode('ascii'),
    ('Time', 'T'): lambda v: datetime.fromisoformat(v.decode())
}


ENCODERS = {
    ('Int', 'I'): lambda v: str(int(v)).encode(),
    ('Float', 'F'): lambda v: str(float(v)).encode(),
    ('Unicode', 'U'): lambda v: v.encode('utf-8'),
    ('ASCII', 'A'): lambda v: v.encode('ascii'),
    ('Time', 'T'): lambda v: v.isoformat().encode()
}


TYPES = {
    int: 'I',
    float: 'F',
    str: 'U',
    datetime: 'T',
}


def raise_decoding_error(annotation, value):
    raise DecodingError(f'unrecognized annotation: {annotation}')


def ensure_encoded(annotation, value):
    if not isinstance(value, bytes):
        raise EncodingError(f'{value=} with {annotation=} is not encoded as bytes')
    return value


def decode_line(stream, decoders=DECODERS, default=raise_decoding_error):
    r'''decode a line

    Arguments:
    stream: a generator compatible with kvnl.load_line()
    decoders: a dict of ways to decode data based on its annotation
        - if None, disable decoding and return a (annotation, raw_value)-tuple
          for the value
        - if {}, let default handle everything
    default: a function which takes the annotation and raw value as inputs
        and returns something suitable:
        - default: raise_decoding_error raises an error
        - None: create an (annotation, raw_value)-tuple

    Yields:
    None while stream yields None
    '\n' if stream yields '\n' and returns
    (key, value) where value depends on decoders and default arguments

    Raises:
    EOFError if data runs out before a valid line is reached
    various errors depending on decoders and default

    Expected behavior:

    No annotation:
    >>> next(decode_line([('x', b'1')]))
    ('x', b'1')

    Long and short forms:
    >>> next(decode_line([('x!I', b'1')]))
    ('x', 1)
    >>> next(decode_line([('x!Int', b'1')]))
    ('x', 1)

    Decoding disabled:
    >>> next(decode_line([('x!I', b'1')], None))
    ('x', ('I', b'1'))
    >>> next(decode_line([ ('x!I', b'1') ], {}, None))
    ('x', ('I', b'1'))

    Decoding forced to default:
    >>> try: next(decode_line([ ('x!I', b'1') ], {}))
    ... except DecodingError: 'DecodingError'
    ...
    'DecodingError'
    >>> next(decode_line([ ('x!complex', b'1+2j') ], {}, lambda a, v: eval(f'{a}({v.decode()})')))
    ('x', (1+2j))

    Nonblocking I/O:
    >>> list(decode_line([None, None, ('x', b'1')]))
    [None, None, ('x', b'1')]

    Types:
    >>> next(decode_line([('x!Float', b'3.14')]))
    ('x', 3.14)
    >>> next(decode_line([('x!Unicode', b'\xcf\x80')]))
    ('x', 'π')
    >>> next(decode_line([('x!ASCII', b'pi')]))
    ('x', 'pi')
    >>> next(decode_line([('!T', b'1234-01-02T04:05:06.789-05:00')]))
    ('', datetime.datetime(1234, 1, 2, 4, 5, 6, 789000, tzinfo=datetime.timezone(datetime.timedelta(days=-1, seconds=68400))))
    '''
    for line in stream:
        if line is None:
            yield
            continue
        if line == '\n':
            yield line
            return
        key, value = line
        if '!' not in key:
            yield key, value
            return

        key, annotation = key.split('!', maxsplit=1)

        if decoders is None:
            yield key, (annotation, value)
            return

        for annotations, decode in decoders.items():
            if annotation in annotations:
                yield key, decode(value)
                return

        if default is not None:
            yield key, default(annotation, value)
            return

        yield key, (annotation, value)
        return

    raise EOFError


def encode_line(key_and_value, encoders=ENCODERS, default=ensure_encoded, types=TYPES):
    r'''encode a line

    Arguments:
    key_and_value: the key and value, which can be:
         - None or '\n', passed on unchanged
         - (key, value) tuple, where value can be:
            - (annotation, value) tuple for an explicit annotation
            - (None, value) tuple to infer annotation from the type of value
            - value alone, which the same as above (unless value is a tuple)
    encoders: dict of rules for encoding values
    types: dict of types and their corresponing annotations

    Returns:
    Generally, values which kvnl.dump_line accepts
    Specifically, None, '\n' or (key: str, value: bytes) pair where
    key is appropriately annotated and value is appropriately encoded

    Raises:
    AnnotationError() is value doesn't not end up being a bytes instance for the given parameters
    various errors depending on encoders

    Expected behavior:

    Basic cases:
    >>> encode_line(None)
    >>> encode_line('\n')
    '\n'

    Automatic encoding:
    >>> encode_line(('x', 1))
    ('x!I', b'1')
    >>> encode_line(('x', 3.14))
    ('x!F', b'3.14')
    >>> encode_line(('x', 'π'))
    ('x!U', b'\xcf\x80')
    >>> from datetime import datetime
    >>> encode_line(('x', datetime.fromisoformat('1234-01-02')))
    ('x!T', b'1234-01-02T00:00:00')

    Explicit annotation:
    >>> encode_line(('x', ('F', 1)))
    ('x!F', b'1.0')

    No annotation:
    >>> encode_line(('x', b'data'))
    ('x', b'data')

    Disabled encoding:
    >>> encode_line(('x', ('F', b'1e0')), encoders=None)
    ('x!F', b'1e0')

    Custom encoding:
    >>> encode_line(('', 1+2j), {}, lambda a, v: str(v).encode())
    ('', b'(1+2j)')
    '''
    if key_and_value in (None, '\n'):
        return key_and_value

    if encoders is None:
        encoders = {}

    if types is None:
        types = {}

    key, value = key_and_value

    if isinstance(value, tuple):
        annotation, value = value
    else:
        annotation = None

    if annotation is None:
        for t, a in types.items():
            if isinstance(value, t):
                annotation = a
                break

    for annotations, encode in encoders.items():
        if annotation in annotations:
            value = encode(value)
            break

    value = default(annotation, value)

    ensure_encoded(annotation, value)

    if annotation is not None:
        key = f'{key}!{annotation}'

    return key, value


def decode_block(stream, decoders=DECODERS, default=raise_decoding_error):
    r'''decode a block of lines'''
    try:
        while True:
            yield from decode_line(stream, decoders)
    except EOFError:
        pass


def encode_block(lines, encoders=ENCODERS, default=ensure_encoded, types=TYPES):
    r'''encode a block of lines'''
    for line in lines:
        yield encode_line(line, encoders, default, types)


if __name__ == '__main__':
    from doctest import testmod
    testmod()
