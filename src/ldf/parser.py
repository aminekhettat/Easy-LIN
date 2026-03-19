"""
LDF (LIN Description File) parser.

Parses LDF files compliant with LIN specification versions 1.3, 2.0, 2.1 and 2.2.
The parser is tolerant of minor formatting differences found in real-world files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes – the structured representation of an LDF file
# ---------------------------------------------------------------------------

@dataclass
class LDFNode:
    """Represents a single LIN node (master or slave)."""
    name: str
    is_master: bool = False
    timebase_ms: float = 0.0
    jitter_ms: float = 0.0


@dataclass
class LDFSignal:
    """Represents a single LIN signal defined in the Signals section."""
    name: str
    bit_length: int
    init_value: int
    publisher: str
    subscribers: list[str] = field(default_factory=list)


@dataclass
class LDFFrameSignal:
    """A signal reference inside a frame, with its bit offset."""
    signal_name: str
    bit_offset: int


@dataclass
class LDFFrame:
    """Represents a LIN frame (message)."""
    name: str
    frame_id: int
    publisher: str
    length: int
    signals: list[LDFFrameSignal] = field(default_factory=list)


@dataclass
class LDFScheduleEntry:
    """One entry in a schedule table."""
    frame_name: str
    delay_ms: float


@dataclass
class LDFScheduleTable:
    """A LIN schedule table."""
    name: str
    entries: list[LDFScheduleEntry] = field(default_factory=list)


@dataclass
class LDFEncodingValue:
    """A single value definition inside a signal encoding type."""
    kind: str          # "logical", "physical", "bcd", "ascii"
    min_value: int = 0
    max_value: int = 0
    scale: float = 1.0
    offset: float = 0.0
    label: str = ""
    unit: str = ""


@dataclass
class LDFEncodingType:
    """A signal encoding type definition."""
    name: str
    values: list[LDFEncodingValue] = field(default_factory=list)


@dataclass
class LDFNodeAttribute:
    """Optional per-node attributes (LIN 2.x)."""
    name: str
    lin_protocol: str = ""
    configured_nad: int = 0
    initial_nad: int = 0
    product_id_supplier: int = 0
    product_id_function: int = 0
    product_id_variant: int = 0
    response_error: str = ""
    fault_state_signals: list[str] = field(default_factory=list)
    p2_min_ms: float = 0.0
    st_min_ms: float = 0.0


@dataclass
class LDFFile:
    """The complete parsed representation of an LDF file."""
    protocol_version: str = ""
    language_version: str = ""
    speed_kbps: float = 19.2
    channel_name: str = ""
    master: Optional[LDFNode] = None
    slaves: list[LDFNode] = field(default_factory=list)
    signals: dict[str, LDFSignal] = field(default_factory=dict)
    frames: dict[str, LDFFrame] = field(default_factory=dict)
    schedule_tables: dict[str, LDFScheduleTable] = field(default_factory=dict)
    encoding_types: dict[str, LDFEncodingType] = field(default_factory=dict)
    signal_representations: dict[str, str] = field(default_factory=dict)
    node_attributes: dict[str, LDFNodeAttribute] = field(default_factory=dict)
    source_path: str = ""


# ---------------------------------------------------------------------------
# Tokeniser helpers
# ---------------------------------------------------------------------------

_COMMENT_RE = re.compile(r'/\*.*?\*/', re.DOTALL)
_LINE_COMMENT_RE = re.compile(r'//[^\n]*')


def _strip_comments(text: str) -> str:
    """Remove C-style block comments and line comments from LDF source."""
    text = _COMMENT_RE.sub(' ', text)
    text = _LINE_COMMENT_RE.sub('', text)
    return text


def _parse_number(value: str) -> int:
    """Parse decimal or hexadecimal integer strings."""
    value = value.strip()
    if value.startswith('0x') or value.startswith('0X'):
        return int(value, 16)
    return int(value, 10)


def _parse_float(value: str) -> float:
    return float(value.strip())


# ---------------------------------------------------------------------------
# Section extractors
# ---------------------------------------------------------------------------

def _find_section(text: str, section_name: str) -> Optional[str]:
    """
    Extract the body (content between outermost braces) of a named section.
    Returns *None* if the section is not present.
    """
    pattern = re.compile(
        r'\b' + re.escape(section_name) + r'\s*\{', re.IGNORECASE
    )
    m = pattern.search(text)
    if not m:
        return None
    start = m.end()  # position just after the opening '{'
    depth = 1
    pos = start
    while pos < len(text) and depth > 0:
        if text[pos] == '{':
            depth += 1
        elif text[pos] == '}':
            depth -= 1
        pos += 1
    return text[start:pos - 1]


def _split_statements(body: str) -> list[str]:
    """
    Split section body into individual statements, respecting nested braces.
    Each statement ends with ';'.  Nested blocks are returned whole.
    """
    statements: list[str] = []
    current: list[str] = []
    depth = 0
    for char in body:
        if char == '{':
            depth += 1
            current.append(char)
        elif char == '}':
            depth -= 1
            current.append(char)
            if depth == 0:
                # Block closed – emit as a statement
                stmt = ''.join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = []
        elif char == ';' and depth == 0:
            stmt = ''.join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(char)
    leftover = ''.join(current).strip()
    if leftover:
        statements.append(leftover)
    return statements


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------

def _parse_header(text: str, ldf: LDFFile) -> None:
    """Parse global header fields (protocol version, speed, …)."""
    m = re.search(r'LIN_protocol_version\s*=\s*"([^"]+)"', text, re.IGNORECASE)
    if m:
        ldf.protocol_version = m.group(1).strip()

    m = re.search(r'LIN_language_version\s*=\s*"([^"]+)"', text, re.IGNORECASE)
    if m:
        ldf.language_version = m.group(1).strip()

    m = re.search(r'LIN_speed\s*=\s*([\d.]+)\s*kbps', text, re.IGNORECASE)
    if m:
        ldf.speed_kbps = _parse_float(m.group(1))

    m = re.search(r'Channel_name\s*=\s*"([^"]+)"', text, re.IGNORECASE)
    if m:
        ldf.channel_name = m.group(1).strip()


def _parse_nodes(body: str, ldf: LDFFile) -> None:
    """Parse the Nodes section."""
    m = re.search(
        r'Master\s*:\s*(\w+)\s*,\s*([\d.]+)\s*ms\s*,\s*([\d.]+)\s*ms',
        body, re.IGNORECASE
    )
    if m:
        ldf.master = LDFNode(
            name=m.group(1),
            is_master=True,
            timebase_ms=_parse_float(m.group(2)),
            jitter_ms=_parse_float(m.group(3)),
        )

    m = re.search(r'Slaves\s*:(.*?)(?:;|$)', body, re.IGNORECASE | re.DOTALL)
    if m:
        raw = m.group(1)
        for name in re.split(r'[,\s]+', raw.strip()):
            name = name.strip().rstrip(';')
            if name:
                ldf.slaves.append(LDFNode(name=name, is_master=False))


def _parse_signals(body: str, ldf: LDFFile) -> None:
    """Parse the Signals section."""
    for stmt in _split_statements(body):
        # SignalName : size, init_value, publisher {, subscriber}* ;
        m = re.match(
            r'(\w+)\s*:\s*(\d+)\s*,\s*(0[xX][\dA-Fa-f]+|\{[^}]+\}|\d+)'
            r'\s*,\s*(\w+)((?:\s*,\s*\w+)*)',
            stmt.strip()
        )
        if not m:
            continue
        name = m.group(1)
        size = int(m.group(2))
        init_raw = m.group(3).strip()
        # Support array init values like {0x00, 0x00}
        if init_raw.startswith('{'):
            init_val = 0
        else:
            init_val = _parse_number(init_raw)
        publisher = m.group(4)
        subs_raw = m.group(5)
        subscribers = [s.strip() for s in subs_raw.split(',') if s.strip()]
        ldf.signals[name] = LDFSignal(
            name=name,
            bit_length=size,
            init_value=init_val,
            publisher=publisher,
            subscribers=subscribers,
        )


def _parse_frames(body: str, ldf: LDFFile) -> None:
    """Parse the Frames section."""
    # Each frame is:  FrameName : id, publisher, length { signals }
    frame_re = re.compile(
        r'(\w+)\s*:\s*(0[xX][\dA-Fa-f]+|\d+)\s*,\s*(\w+)\s*,\s*(\d+)\s*\{([^}]*)\}',
        re.DOTALL
    )
    for m in frame_re.finditer(body):
        name = m.group(1)
        fid = _parse_number(m.group(2))
        publisher = m.group(3)
        length = int(m.group(4))
        signals_body = m.group(5)

        frame_signals: list[LDFFrameSignal] = []
        for sig_stmt in _split_statements(signals_body):
            sm = re.match(r'(\w+)\s*,\s*(\d+)', sig_stmt.strip())
            if sm:
                frame_signals.append(
                    LDFFrameSignal(signal_name=sm.group(1), bit_offset=int(sm.group(2)))
                )

        ldf.frames[name] = LDFFrame(
            name=name,
            frame_id=fid,
            publisher=publisher,
            length=length,
            signals=frame_signals,
        )


def _parse_schedule_tables(body: str, ldf: LDFFile) -> None:
    """Parse the Schedule_tables section."""
    # Each table:  TableName { FrameName delay ms ; ... }
    table_re = re.compile(r'(\w+)\s*\{([^}]*)\}', re.DOTALL)
    for m in table_re.finditer(body):
        tname = m.group(1)
        entries_body = m.group(2)
        table = LDFScheduleTable(name=tname)
        for stmt in _split_statements(entries_body):
            em = re.match(r'(\w+)\s+delay\s+([\d.]+)\s*ms', stmt.strip(), re.IGNORECASE)
            if em:
                table.entries.append(
                    LDFScheduleEntry(frame_name=em.group(1), delay_ms=float(em.group(2)))
                )
        ldf.schedule_tables[tname] = table


def _parse_encoding_types(body: str, ldf: LDFFile) -> None:
    """Parse the Signal_encoding_types section."""
    enc_re = re.compile(r'(\w+)\s*\{([^}]*)\}', re.DOTALL)
    for m in enc_re.finditer(body):
        ename = m.group(1)
        values_body = m.group(2)
        enc = LDFEncodingType(name=ename)

        for stmt in _split_statements(values_body):
            stmt = stmt.strip()
            # logical_value, value, "label" ;
            lv = re.match(
                r'logical_value\s*,\s*(0[xX][\dA-Fa-f]+|\d+)\s*(?:,\s*"([^"]*)")?',
                stmt, re.IGNORECASE
            )
            if lv:
                enc.values.append(LDFEncodingValue(
                    kind='logical',
                    min_value=_parse_number(lv.group(1)),
                    max_value=_parse_number(lv.group(1)),
                    label=lv.group(2) or '',
                ))
                continue

            # physical_value, min, max, scale, offset, "unit" ;
            pv = re.match(
                r'physical_value\s*,\s*(0[xX][\dA-Fa-f]+|\d+)'
                r'\s*,\s*(0[xX][\dA-Fa-f]+|\d+)'
                r'\s*,\s*([\d.eE+-]+)\s*,\s*([\d.eE+-]+)'
                r'(?:\s*,\s*"([^"]*)")?',
                stmt, re.IGNORECASE
            )
            if pv:
                enc.values.append(LDFEncodingValue(
                    kind='physical',
                    min_value=_parse_number(pv.group(1)),
                    max_value=_parse_number(pv.group(2)),
                    scale=float(pv.group(3)),
                    offset=float(pv.group(4)),
                    unit=pv.group(5) or '',
                ))
                continue

            if re.match(r'bcd_value', stmt, re.IGNORECASE):
                enc.values.append(LDFEncodingValue(kind='bcd'))
                continue

            if re.match(r'ascii_value', stmt, re.IGNORECASE):
                enc.values.append(LDFEncodingValue(kind='ascii'))

        ldf.encoding_types[ename] = enc


def _parse_signal_representation(body: str, ldf: LDFFile) -> None:
    """Parse the Signal_representation section."""
    for stmt in _split_statements(body):
        m = re.match(r'(\w+)\s*:(.*)', stmt.strip())
        if m:
            enc_name = m.group(1)
            for sig in re.split(r'[,\s]+', m.group(2).strip()):
                sig = sig.strip().rstrip(';')
                if sig:
                    ldf.signal_representations[sig] = enc_name


def _parse_node_attributes(body: str, ldf: LDFFile) -> None:
    """Parse the Node_attributes section (LIN 2.x)."""
    node_re = re.compile(r'(\w+)\s*\{([^}]*)\}', re.DOTALL)
    for m in node_re.finditer(body):
        nname = m.group(1)
        attrs_body = m.group(2)
        attr = LDFNodeAttribute(name=nname)

        def _field(pattern: str) -> Optional[re.Match]:
            return re.search(pattern, attrs_body, re.IGNORECASE)

        fm = _field(r'LIN_protocol\s*=\s*"([^"]+)"')
        if fm:
            attr.lin_protocol = fm.group(1)

        fm = _field(r'configured_NAD\s*=\s*(0[xX][\dA-Fa-f]+|\d+)')
        if fm:
            attr.configured_nad = _parse_number(fm.group(1))

        fm = _field(r'initial_NAD\s*=\s*(0[xX][\dA-Fa-f]+|\d+)')
        if fm:
            attr.initial_nad = _parse_number(fm.group(1))

        fm = _field(r'product_id\s*=\s*(0[xX][\dA-Fa-f]+|\d+)\s*,'
                    r'\s*(0[xX][\dA-Fa-f]+|\d+)\s*,\s*(0[xX][\dA-Fa-f]+|\d+)')
        if fm:
            attr.product_id_supplier = _parse_number(fm.group(1))
            attr.product_id_function = _parse_number(fm.group(2))
            attr.product_id_variant = _parse_number(fm.group(3))

        fm = _field(r'response_error\s*=\s*(\w+)')
        if fm:
            attr.response_error = fm.group(1)

        fm = _field(r'P2_min\s*=\s*([\d.]+)\s*ms')
        if fm:
            attr.p2_min_ms = float(fm.group(1))

        fm = _field(r'ST_min\s*=\s*([\d.]+)\s*ms')
        if fm:
            attr.st_min_ms = float(fm.group(1))

        ldf.node_attributes[nname] = attr


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class LDFParser:
    """Parse LDF files into an :class:`LDFFile` data structure."""

    def parse_file(self, path: str | Path) -> LDFFile:
        """Parse a LDF file from *path* and return an :class:`LDFFile`."""
        path = Path(path)
        text = path.read_text(encoding='utf-8', errors='replace')
        ldf = self.parse_string(text)
        ldf.source_path = str(path)
        return ldf

    def parse_string(self, text: str) -> LDFFile:
        """Parse LDF content given as a string and return an :class:`LDFFile`."""
        text = _strip_comments(text)
        ldf = LDFFile()

        _parse_header(text, ldf)

        nodes_body = _find_section(text, 'Nodes')
        if nodes_body:
            _parse_nodes(nodes_body, ldf)

        signals_body = _find_section(text, 'Signals')
        if signals_body:
            _parse_signals(signals_body, ldf)

        frames_body = _find_section(text, 'Frames')
        if frames_body:
            _parse_frames(frames_body, ldf)

        schedule_body = _find_section(text, 'Schedule_tables')
        if schedule_body:
            _parse_schedule_tables(schedule_body, ldf)

        enc_body = _find_section(text, 'Signal_encoding_types')
        if enc_body:
            _parse_encoding_types(enc_body, ldf)

        repr_body = _find_section(text, 'Signal_representation')
        if repr_body:
            _parse_signal_representation(repr_body, ldf)

        node_attr_body = _find_section(text, 'Node_attributes')
        if node_attr_body:
            _parse_node_attributes(node_attr_body, ldf)

        return ldf
