"""WordprocessingML byte kernels exposed through a small C ABI."""

from std.algorithm import parallelize
from std.sys.info import simd_width_of as simdwidthof

comptime BPtr = UnsafePointer[UInt8, AnyOrigin[mut=True]]
comptime IPtr = UnsafePointer[Int64, AnyOrigin[mut=True]]
comptime W = simdwidthof[DType.float64]()
comptime BYTE_W = W * 8
comptime ESCAPE_TASKS = 16
comptime PARALLEL_ESCAPE_BYTES = 1_048_576


def copy_plain(src: BPtr, start: Int, count: Int, dst: BPtr, pos: Int) -> Int:
    var offset = 0
    while offset + BYTE_W <= count:
        dst.store[alignment=1](
            pos + offset,
            src.load[width=BYTE_W, alignment=1](start + offset),
        )
        offset += BYTE_W
    while offset < count:
        dst[pos + offset] = src[start + offset]
        offset += 1
    return pos + count


def put_entity(dst: BPtr, pos: Int, kind: Int) -> Int:
    var p = pos
    dst[p] = UInt8(38)
    p += 1
    if kind == 0:
        dst[p] = UInt8(97)
        dst[p + 1] = UInt8(109)
        dst[p + 2] = UInt8(112)
        dst[p + 3] = UInt8(59)
        return p + 4
    if kind == 1:
        dst[p] = UInt8(108)
        dst[p + 1] = UInt8(116)
        dst[p + 2] = UInt8(59)
        return p + 3
    if kind == 2:
        dst[p] = UInt8(103)
        dst[p + 1] = UInt8(116)
        dst[p + 2] = UInt8(59)
        return p + 3
    if kind == 3:
        dst[p] = UInt8(113)
        dst[p + 1] = UInt8(117)
        dst[p + 2] = UInt8(111)
        dst[p + 3] = UInt8(116)
        dst[p + 4] = UInt8(59)
        return p + 5
    dst[p] = UInt8(35)
    if kind == 4:
        dst[p + 1] = UInt8(57)
    elif kind == 5:
        dst[p + 1] = UInt8(49)
        dst[p + 2] = UInt8(48)
        dst[p + 3] = UInt8(59)
        return p + 4
    else:
        dst[p + 1] = UInt8(49)
        dst[p + 2] = UInt8(51)
        dst[p + 3] = UInt8(59)
        return p + 4
    dst[p + 2] = UInt8(59)
    return p + 3


def escape_one(
    src: BPtr, start: Int, count: Int, dst: BPtr, pos: Int, attribute: Bool
) -> Int:
    var p = pos
    var plain_start = start
    var i = start
    var end = start + count
    while i < end:
        if i + BYTE_W <= end:
            var values = src.load[width=BYTE_W, alignment=1](i)
            var special = (
                values.eq(SIMD[DType.uint8, BYTE_W](38))
                | values.eq(SIMD[DType.uint8, BYTE_W](60))
                | values.eq(SIMD[DType.uint8, BYTE_W](62))
            )
            if attribute:
                special |= (
                    values.eq(SIMD[DType.uint8, BYTE_W](34))
                    | values.eq(SIMD[DType.uint8, BYTE_W](9))
                    | values.eq(SIMD[DType.uint8, BYTE_W](10))
                    | values.eq(SIMD[DType.uint8, BYTE_W](13))
                )
            if not special.reduce_or():
                i += BYTE_W
                continue
        var c = src[i]
        var kind = -1
        if c == UInt8(38):
            kind = 0
        elif c == UInt8(60):
            kind = 1
        elif c == UInt8(62):
            kind = 2
        elif attribute and c == UInt8(34):
            kind = 3
        elif attribute and c == UInt8(9):
            kind = 4
        elif attribute and c == UInt8(10):
            kind = 5
        elif attribute and c == UInt8(13):
            kind = 6
        if kind >= 0:
            p = copy_plain(src, plain_start, i - plain_start, dst, p)
            p = put_entity(dst, p, kind)
            plain_start = i + 1
        i += 1
    return copy_plain(src, plain_start, end - plain_start, dst, p)


def escaped_size(
    src: BPtr, start: Int, count: Int, attribute: Bool
) -> Int:
    var size = count
    var i = start
    var end = start + count
    while i < end:
        if i + BYTE_W <= end:
            var values = src.load[width=BYTE_W, alignment=1](i)
            var special = (
                values.eq(SIMD[DType.uint8, BYTE_W](38))
                | values.eq(SIMD[DType.uint8, BYTE_W](60))
                | values.eq(SIMD[DType.uint8, BYTE_W](62))
            )
            if attribute:
                special |= (
                    values.eq(SIMD[DType.uint8, BYTE_W](34))
                    | values.eq(SIMD[DType.uint8, BYTE_W](9))
                    | values.eq(SIMD[DType.uint8, BYTE_W](10))
                    | values.eq(SIMD[DType.uint8, BYTE_W](13))
                )
            if not special.reduce_or():
                i += BYTE_W
                continue
        var c = src[i]
        if c == UInt8(38):
            size += 4
        elif c == UInt8(60) or c == UInt8(62):
            size += 3
        elif attribute and c == UInt8(34):
            size += 5
        elif attribute and c == UInt8(9):
            size += 3
        elif attribute and (c == UInt8(10) or c == UInt8(13)):
            size += 4
        i += 1
    return size


@export("mdx_escape_one")
def mdx_escape_one(
    src_addr: Int,
    count: Int,
    dst_addr: Int,
    dst_capacity: Int,
    attribute: Int,
    scratch_addr: Int,
) abi("C") -> Int:
    if src_addr == 0 or dst_addr == 0 or count < 0 or dst_capacity < 0:
        return -1
    if count > dst_capacity // 6:
        return -1
    var src = BPtr(unsafe_from_address=src_addr)
    var dst = BPtr(unsafe_from_address=dst_addr)
    var is_attribute = attribute != 0
    if count < PARALLEL_ESCAPE_BYTES:
        return escape_one(src, 0, count, dst, 0, is_attribute)

    if scratch_addr == 0:
        return -1
    var scratch = IPtr(unsafe_from_address=scratch_addr)

    @parameter
    def count_chunk(task: Int):
        var start = count * task // ESCAPE_TASKS
        var end = count * (task + 1) // ESCAPE_TASKS
        scratch[task] = Int64(
            escaped_size(src, start, end - start, is_attribute)
        )

    parallelize[count_chunk](ESCAPE_TASKS, ESCAPE_TASKS)
    var total = 0
    for task in range(ESCAPE_TASKS):
        var size = Int(scratch[task])
        scratch[task] = Int64(total)
        total += size
        if total < 0 or total > dst_capacity:
            return -1
    scratch[ESCAPE_TASKS] = Int64(total)

    @parameter
    def write_chunk(task: Int):
        var start = count * task // ESCAPE_TASKS
        var end = count * (task + 1) // ESCAPE_TASKS
        _ = escape_one(
            src,
            start,
            end - start,
            dst,
            Int(scratch[task]),
            is_attribute,
        )

    parallelize[write_chunk](ESCAPE_TASKS, ESCAPE_TASKS)
    return total


@export("mdx_escape_batch")
def mdx_escape_batch(
    src_addr: Int,
    src_size: Int,
    offsets_addr: Int,
    lengths_addr: Int,
    count: Int,
    dst_addr: Int,
    dst_capacity: Int,
    dst_offsets_addr: Int,
    attribute: Int,
) abi("C") -> Int:
    if (
        src_addr == 0 or offsets_addr == 0 or lengths_addr == 0
        or dst_addr == 0 or dst_offsets_addr == 0 or src_size < 0
        or count < 0 or dst_capacity < 0
    ):
        return -1
    var src = BPtr(unsafe_from_address=src_addr)
    var offsets = IPtr(unsafe_from_address=offsets_addr)
    var lengths = IPtr(unsafe_from_address=lengths_addr)
    var dst = BPtr(unsafe_from_address=dst_addr)
    var dst_offsets = IPtr(unsafe_from_address=dst_offsets_addr)
    var p = 0
    for i in range(count):
        var start = Int(offsets[i])
        var length = Int(lengths[i])
        if start < 0 or length < 0 or start > src_size or length > src_size - start:
            return -1
        var required = escaped_size(src, start, length, attribute != 0)
        if required < 0 or required > dst_capacity - p:
            return -1
        dst_offsets[i] = Int64(p)
        p = escape_one(
            src, start, length, dst, p, attribute != 0
        )
    dst_offsets[count] = Int64(p)
    return p


def same_local_name(src: BPtr, start: Int, end: Int, a: Int, b: Int, c: Int) -> Bool:
    var local = start
    for i in range(start, end):
        if src[i] == UInt8(58):
            local = i + 1
    var length = end - local
    if length == 1:
        return src[local] == UInt8(a)
    if length == 2:
        return src[local] == UInt8(a) and src[local + 1] == UInt8(b)
    if length == 3:
        return (
            src[local] == UInt8(a)
            and src[local + 1] == UInt8(b)
            and src[local + 2] == UInt8(c)
        )
    return False


@export("mdx_analyze_xml")
def mdx_analyze_xml(src_addr: Int, n: Int, counts_addr: Int) abi("C") -> Int:
    if src_addr == 0 or counts_addr == 0 or n < 0:
        return -1
    var src = BPtr(unsafe_from_address=src_addr)
    var counts = IPtr(unsafe_from_address=counts_addr)
    for i in range(6):
        counts[i] = 0
    var pos = 0
    var tags = 0
    while pos < n:
        if src[pos] != UInt8(60):
            pos += 1
            continue
        var i = pos + 1
        if i >= n:
            break
        if src[i] == UInt8(47) or src[i] == UInt8(33) or src[i] == UInt8(63):
            pos += 1
            continue
        var start = i
        while i < n:
            var c = src[i]
            if (
                c == UInt8(32) or c == UInt8(9) or c == UInt8(10)
                or c == UInt8(13) or c == UInt8(47) or c == UInt8(62)
            ):
                break
            i += 1
        tags += 1
        if same_local_name(src, start, i, 112, 0, 0):
            counts[1] += 1
        elif same_local_name(src, start, i, 114, 0, 0):
            counts[2] += 1
        elif same_local_name(src, start, i, 116, 0, 0):
            counts[3] += 1
        elif same_local_name(src, start, i, 116, 98, 108):
            counts[4] += 1
        elif same_local_name(src, start, i, 116, 114, 0):
            counts[5] += 1
        pos = i
    counts[0] = Int64(tags)
    return tags
