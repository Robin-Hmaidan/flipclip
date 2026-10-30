from pathlib import Path

from python_multipart.multipart import MultipartParser, parse_options_header
from starlette.requests import Request

FILE_FIELD = b"file"
# Room for boundaries and part headers on top of the file itself.
MULTIPART_OVERHEAD = 64 * 1024


class UploadTooLarge(Exception):
    pass


class UploadMalformed(Exception):
    pass


async def stream_upload(request: Request, dest: Path, max_bytes: int) -> int:
    """Write the multipart field "file" to dest chunk by chunk; return its size.

    FastAPI's UploadFile would buffer the whole body before the handler runs, so the size
    limit could only be checked after the fact. Parsing the raw stream lets us stop early.
    """
    content_type, params = parse_options_header(request.headers.get("content-type"))
    boundary = params.get(b"boundary")
    if content_type != b"multipart/form-data" or not boundary:
        raise UploadMalformed("not multipart/form-data")

    state = {"capturing": False, "found": False, "written": 0}
    headers: dict[bytes, bytes] = {}
    name, value = bytearray(), bytearray()

    def on_part_begin() -> None:
        state["capturing"] = False
        headers.clear()

    def on_header_field(data: bytes, start: int, end: int) -> None:
        name.extend(data[start:end])

    def on_header_value(data: bytes, start: int, end: int) -> None:
        value.extend(data[start:end])

    def on_header_end() -> None:
        headers[bytes(name).lower()] = bytes(value)
        name.clear()
        value.clear()

    def on_headers_finished() -> None:
        _, disposition = parse_options_header(headers.get(b"content-disposition"))
        # Only the first "file" part with a filename is kept; any other field is skipped.
        if not state["found"] and disposition.get(b"name") == FILE_FIELD and b"filename" in disposition:
            state["capturing"] = state["found"] = True

    def on_part_data(data: bytes, start: int, end: int) -> None:
        if not state["capturing"]:
            return
        state["written"] += end - start
        if state["written"] > max_bytes:
            raise UploadTooLarge()
        out.write(data[start:end])

    def on_part_end() -> None:
        state["capturing"] = False

    parser = MultipartParser(boundary, {
        "on_part_begin": on_part_begin,
        "on_header_field": on_header_field,
        "on_header_value": on_header_value,
        "on_header_end": on_header_end,
        "on_headers_finished": on_headers_finished,
        "on_part_data": on_part_data,
        "on_part_end": on_part_end,
    })

    total = 0
    with dest.open("wb") as out:
        try:
            async for chunk in request.stream():
                # Counts the whole body too, so huge non-file fields can't bypass the limit.
                total += len(chunk)
                if total > max_bytes + MULTIPART_OVERHEAD:
                    raise UploadTooLarge()
                parser.write(chunk)
            parser.finalize()
        except ValueError as exc:  # python-multipart parse errors subclass ValueError
            raise UploadMalformed(str(exc)) from exc

    if not state["found"] or state["written"] == 0:
        raise UploadMalformed("no file in field 'file'")
    return state["written"]
