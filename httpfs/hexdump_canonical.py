# based on
# https://github.com/walchko/pyhexdump/blob/master/pyhexdump/pyhexdump.py
# https://www.geoffreybrown.com/blog/a-hexdump-program-in-python/

# FIXME stop at end of file
# TODO produce same output as 'hexdump -C'

def hexdump_canonical(data, cols=80):
    # print the header
    print('hexdump: {} bytes'.format(len(data)))
    if False:
        print('{:>6} {:02x} {:02x} {:02x} {:02x} {:02x} {:02x} {:02x} {:02x} {:02x}  {:02x} {:02x} {:02x} {:02x} {:02x} {:02x} {:02x}  |{}|'.format(
            'Offset(h)',
            0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
            'String'
        ))
        print('-'*cols)

    # formating string for each line
    print_string = '{:08x}  {:02x} {:02x} {:02x} {:02x} {:02x} {:02x} {:02x} {:02x}  {:02x} {:02x} {:02x} {:02x} {:02x} {:02x} {:02x} {:02x}  |{}|'

    # break data up into 16 byte chunks
    size = 16
    buff = []
    line = [0]*size
    for i, char in enumerate(data):
        if i % size == 0 and i != 0:
            buff.append(line)
            line = [0]*size
            line[0] = char
        else:
            line[i % size] = char

            if i == len(data) - 1:
                buff.append(line)

    # print data out
    for i, line in enumerate(buff):
        print(print_string.format(
            i * 16,
            line[0],
            line[1],
            line[2],
            line[3],
            line[4],
            line[5],
            line[6],
            line[7],
            line[8],
            line[9],
            line[10],
            line[11],
            line[12],
            line[13],
            line[14],
            line[15],
            get_printable(line)
        ))

def get_printable(a):
    b = []
    for c in a:
        if 0x7e >= c >= 0x20:  # only print ascii chars
            b.append(chr(c))
        else:  # all others just replace with '.'
            b.append('.')
    ret = ''.join(b)
    return ret

