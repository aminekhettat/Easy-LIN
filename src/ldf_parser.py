"""Primary Easy-LIN LDF parser.

Parses LDF files conforming to LIN specification versions 1.3, 2.0, 2.1, and
2.2, and produces structured data objects that describe the entire LIN
network.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.5.0
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
    in LICENSE.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class LDFMaster:
    """LIN master node description."""

    name: str
    time_base: float  # ms
    jitter: float  # ms


@dataclass
class LDFNodes:
    """Nodes section of an LDF file."""

    master: LDFMaster
    slaves: List[str]


@dataclass
class LDFSignal:
    """Single signal definition."""

    name: str
    size: int  # bits
    init_value: int  # initial / default value
    publisher: str
    subscribers: List[str]


@dataclass
class LDFFrameSignal:
    """Signal placement inside a frame."""

    signal_name: str
    bit_offset: int


@dataclass
class LDFFrame:
    """Frame (message) definition."""

    name: str
    frame_id: int  # 0x00-0x3B for normal frames
    publisher: str
    frame_size: int  # bytes (1-8)
    signals: List[LDFFrameSignal] = field(default_factory=list)


@dataclass
class LDFScheduleEntry:
    """One entry in a schedule table."""

    frame_name: str
    delay: float  # ms


@dataclass
class LDFScheduleTable:
    """A named schedule table."""

    name: str
    entries: List[LDFScheduleEntry] = field(default_factory=list)


@dataclass
class LDFLogicalValue:
    """Symbolic name for a signal value."""

    signal_value: int
    text: str


@dataclass
class LDFPhysicalRange:
    """Physical representation range for a signal."""

    min_value: int
    max_value: int
    scale: float
    offset: float
    unit: str


@dataclass
class LDFEncodingType:
    """Signal encoding / representation type."""

    name: str
    logical_values: List[LDFLogicalValue] = field(default_factory=list)
    physical_ranges: List[LDFPhysicalRange] = field(default_factory=list)
    bcd: bool = False
    ascii: bool = False


@dataclass
class LDFSignalRepresentation:
    """Associates an encoding type with one or more signals."""

    encoding_type: str
    signals: List[str] = field(default_factory=list)


@dataclass
class LDFNodeAttributes:
    """LIN 2.x node attributes block."""

    node_name: str
    lin_protocol: str = ""
    configured_nad: int = 0
    initial_nad: int = 0
    product_id_supplier: int = 0
    product_id_function: int = 0
    product_id_variant: int = 0
    response_error: str = ""
    p2_min: float = 0.0
    st_min: float = 0.0
    n_as_timeout: float = 0.0
    n_cr_timeout: float = 0.0
    configurable_frames: List[str] = field(default_factory=list)


@dataclass
class LDFFile:
    """Complete parsed representation of an LDF file."""

    protocol_version: str = "2.0"
    language_version: str = "2.0"
    speed: float = 19.2  # kbps
    channel_name: Optional[str] = None
    nodes: Optional[LDFNodes] = None
    signals: List[LDFSignal] = field(default_factory=list)
    frames: List[LDFFrame] = field(default_factory=list)
    schedule_tables: List[LDFScheduleTable] = field(default_factory=list)
    encoding_types: List[LDFEncodingType] = field(default_factory=list)
    signal_representations: List[LDFSignalRepresentation] = field(default_factory=list)
    node_attributes: List[LDFNodeAttributes] = field(default_factory=list)

    # Convenience lookups (populated after parse)
    _signals_by_name: Dict[str, LDFSignal] = field(default_factory=dict, repr=False)
    _frames_by_name: Dict[str, LDFFrame] = field(default_factory=dict, repr=False)
    _frames_by_id: Dict[int, LDFFrame] = field(default_factory=dict, repr=False)

    def build_lookups(self) -> None:
        """Build name/id → object lookup tables for quick access."""
        self._signals_by_name = {s.name: s for s in self.signals}
        self._frames_by_name = {f.name: f for f in self.frames}
        self._frames_by_id = {f.frame_id: f for f in self.frames}

    def signal(self, name: str) -> Optional[LDFSignal]:
        """Return the signal with the given name, if it exists."""
        return self._signals_by_name.get(name)

    def frame_by_name(self, name: str) -> Optional[LDFFrame]:
        """Return the frame with the given name, if it exists."""
        return self._frames_by_name.get(name)

    def frame_by_id(self, frame_id: int) -> Optional[LDFFrame]:
        """Return the frame with the given identifier, if it exists."""
        return self._frames_by_id.get(frame_id)


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r'"[^"]*"'  # quoted string
    r"|0[xX][0-9A-Fa-f]+"  # hex integer
    r"|\d+\.\d+"  # float
    r"|\d+"  # integer
    r"|[A-Za-z_][A-Za-z0-9_.]*"  # identifier (allow dots for version strings)
    r"|[{}:;=,\-]"  # single-char punctuation (including minus)
)


def _remove_comments(text: str) -> str:
    """Strip // line comments and /* … */ block comments."""
    # Block comments first
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    # Line comments
    text = re.sub(r"//[^\n]*", " ", text)
    return text


def _tokenize(text: str) -> List[str]:
    """Tokenize LDF source text after comment removal."""
    return _TOKEN_RE.findall(_remove_comments(text))


# ---------------------------------------------------------------------------
# Parser helpers
# ---------------------------------------------------------------------------


class _Parser:
    """Token-stream parser for LDF files."""

    def __init__(self, tokens: List[str]) -> None:
        """Initialize the parser with a flat token sequence."""
        self._tokens = tokens
        self._pos = 0

    # --- low-level helpers ---------------------------------------------------

    def _peek(self) -> Optional[str]:
        """Return the current token without consuming it."""
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _consume(self) -> str:
        """Consume and return the current token."""
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expect(self, value: str) -> str:
        """Consume the next token and verify its exact value."""
        tok = self._consume()
        if tok != value:
            raise LDFParseError(
                f"Expected '{value}' but got '{tok}' (near token index {self._pos})"
            )
        return tok

    def _expect_semi(self) -> None:
        """Consume the statement terminator token."""
        self._expect(";")

    def _expect_identifier(self) -> str:
        """Consume and validate one identifier token."""
        tok = self._consume()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_.]*$", tok):
            raise LDFParseError(f"Expected identifier, got '{tok}'")
        return tok

    # --- number helpers ------------------------------------------------------

    def _consume_number(self) -> int:
        """Consume an optional minus sign and an integer token, return the int value."""
        sign = 1
        if self._peek() == "-":
            self._consume()
            sign = -1
        return sign * self._parse_number(self._consume())

    def _consume_float(self) -> float:
        """Consume an optional minus sign and a numeric token, return the float value."""
        sign = 1.0
        if self._peek() == "-":
            self._consume()
            sign = -1.0
        return sign * self._parse_float(self._consume())

    @staticmethod
    def _parse_number(tok: str) -> int:
        """Parse a decimal or hex integer token."""
        tok = tok.strip()
        if tok.startswith("0x") or tok.startswith("0X"):
            return int(tok, 16)
        try:
            return int(tok, 10)
        except ValueError:
            return int(float(tok))

    @staticmethod
    def _parse_float(tok: str) -> float:
        """Parse a floating-point token."""
        return float(tok)

    @staticmethod
    def _strip_quotes(tok: str) -> str:
        """Remove surrounding double quotes from a token when present."""
        if tok.startswith('"') and tok.endswith('"'):
            return tok[1:-1]
        return tok

    # --- top-level parse -----------------------------------------------------

    def parse(self) -> LDFFile:
        """Parse the token stream into an :class:`LDFFile` object."""
        ldf = LDFFile()
        # First token should be 'LIN_description_file'
        if self._peek() == "LIN_description_file":
            self._consume()
            self._expect_semi()

        while self._peek() is not None:
            tok = self._peek()
            if tok == "LIN_protocol_version":
                self._consume()
                self._expect("=")
                ldf.protocol_version = self._strip_quotes(self._consume())
                self._expect_semi()
            elif tok == "LIN_language_version":
                self._consume()
                self._expect("=")
                ldf.language_version = self._strip_quotes(self._consume())
                self._expect_semi()
            elif tok == "LIN_speed":
                self._consume()
                self._expect("=")
                ldf.speed = self._consume_float()
                # optional unit 'kbps'
                if self._peek() == "kbps":
                    self._consume()
                self._expect_semi()
            elif tok == "Channel_name":
                self._consume()
                self._expect("=")
                ldf.channel_name = self._strip_quotes(self._consume())
                self._expect_semi()
            elif tok == "Nodes":
                self._consume()
                ldf.nodes = self._parse_nodes()
            elif tok == "Signals":
                self._consume()
                ldf.signals = self._parse_signals()
            elif tok == "Frames":
                self._consume()
                ldf.frames = self._parse_frames()
            elif tok == "Diagnostic_frames":
                self._consume()
                self._skip_block()
            elif tok == "Sporadic_frames":
                self._consume()
                self._skip_block()
            elif tok == "Event_triggered_frames":
                self._consume()
                self._skip_block()
            elif tok == "Schedule_tables":
                self._consume()
                ldf.schedule_tables = self._parse_schedule_tables()
            elif tok == "Signal_groups":
                self._consume()
                self._skip_block()
            elif tok == "Signal_encoding_types":
                self._consume()
                ldf.encoding_types = self._parse_encoding_types()
            elif tok == "Signal_representation":
                self._consume()
                ldf.signal_representations = self._parse_signal_representations()
            elif tok == "Node_attributes":
                self._consume()
                ldf.node_attributes = self._parse_node_attributes()
            elif tok == "Node_composition":
                self._consume()
                self._skip_block()
            elif tok == "Composite":
                self._consume()
                self._skip_block()
            else:
                # Unknown keyword — skip to next ';' or block
                self._consume()

        ldf.build_lookups()
        return ldf

    # --- section parsers -----------------------------------------------------

    def _parse_nodes(self) -> LDFNodes:
        """Parse the ``Nodes`` section."""
        self._expect("{")
        self._expect("Master")
        self._expect(":")
        master_name = self._expect_identifier()
        self._expect(",")
        time_base = self._consume_float()
        if self._peek() == "ms":
            self._consume()
        self._expect(",")
        jitter = self._consume_float()
        if self._peek() == "ms":
            self._consume()
        self._expect_semi()

        master = LDFMaster(name=master_name, time_base=time_base, jitter=jitter)

        slaves: List[str] = []
        if self._peek() == "Slaves":
            self._consume()
            self._expect(":")
            while self._peek() not in (";", "}", None):
                name = self._consume()
                if name == ",":
                    continue
                slaves.append(name)
            self._expect_semi()

        self._expect("}")
        return LDFNodes(master=master, slaves=slaves)

    def _parse_signals(self) -> List[LDFSignal]:
        """Parse the ``Signals`` section."""
        signals: List[LDFSignal] = []
        self._expect("{")
        while self._peek() != "}":
            if self._peek() is None:  # pragma: no cover - defensive EOF guard
                break
            name = self._expect_identifier()
            self._expect(":")
            size = self._consume_number()
            self._expect(",")
            # init value may be hex or decimal
            init_tok = self._consume()
            # init_value might be a hex array {0x00, …} — skip for now, use 0
            if init_tok == "{":
                while self._consume() != "}":
                    pass
                init_value = 0
            else:
                init_value = self._parse_number(init_tok)
            self._expect(",")
            publisher = self._expect_identifier()
            subscribers: List[str] = []
            while self._peek() == ",":
                self._consume()
                subscribers.append(self._expect_identifier())
            self._expect_semi()
            signals.append(
                LDFSignal(
                    name=name,
                    size=size,
                    init_value=init_value,
                    publisher=publisher,
                    subscribers=subscribers,
                )
            )
        self._expect("}")
        return signals

    def _parse_frames(self) -> List[LDFFrame]:
        """Parse the ``Frames`` section."""
        frames: List[LDFFrame] = []
        known_sections = {
            "Nodes",
            "Signals",
            "Frames",
            "Diagnostic_frames",
            "Sporadic_frames",
            "Event_triggered_frames",
            "Schedule_tables",
            "Signal_groups",
            "Signal_encoding_types",
            "Signal_representation",
            "Node_attributes",
            "Node_composition",
            "Composite",
        }
        self._expect("{")
        while self._peek() != "}":
            if self._peek() is None:  # pragma: no cover - defensive EOF guard
                break
            name = self._expect_identifier()
            if name in known_sections and self._peek() == "{":
                # Some vendor LDFs omit the final '}' for Frames and jump directly
                # to the next top-level section.
                self._pos -= 1
                break
            self._expect(":")
            frame_id = self._consume_number()
            self._expect(",")
            publisher = self._expect_identifier()
            self._expect(",")
            frame_size = self._consume_number()
            self._expect("{")
            sig_refs: List[LDFFrameSignal] = []
            while self._peek() != "}":
                if self._peek() is None:  # pragma: no cover - defensive EOF guard
                    break
                sig_name = self._expect_identifier()
                if self._peek() == ":":
                    # Some vendor LDF files repeat a full frame header inside a frame block.
                    # Tolerate and descend into that nested signal block.
                    self._consume()
                    _ = self._consume_number()
                    self._expect(",")
                    _ = self._expect_identifier()
                    self._expect(",")
                    _ = self._consume_number()
                    self._expect("{")
                    continue
                self._expect(",")
                offset = self._consume_number()
                self._expect_semi()
                sig_refs.append(LDFFrameSignal(signal_name=sig_name, bit_offset=offset))
            self._expect("}")
            frames.append(
                LDFFrame(
                    name=name,
                    frame_id=frame_id,
                    publisher=publisher,
                    frame_size=frame_size,
                    signals=sig_refs,
                )
            )
        if self._peek() == "}":
            self._expect("}")
        return frames

    def _parse_schedule_tables(self) -> List[LDFScheduleTable]:
        """Parse the ``Schedule_tables`` section."""
        tables: List[LDFScheduleTable] = []
        self._expect("{")
        while self._peek() != "}":
            if self._peek() is None:  # pragma: no cover - defensive EOF guard
                break
            table_name = self._expect_identifier()
            self._expect("{")
            entries: List[LDFScheduleEntry] = []
            while self._peek() != "}":
                if self._peek() is None:  # pragma: no cover - defensive EOF guard
                    break
                # Frame name or special command (AssignNAD, FreeFormat, …)
                frame_or_cmd = self._expect_identifier()
                # Commands like AssignNAD have a sub-block
                if self._peek() == "{":
                    self._skip_block()
                self._expect("delay")
                delay = self._consume_float()
                if self._peek() == "ms":
                    self._consume()
                self._expect_semi()
                entries.append(LDFScheduleEntry(frame_name=frame_or_cmd, delay=delay))
            self._expect("}")
            tables.append(LDFScheduleTable(name=table_name, entries=entries))
        self._expect("}")
        return tables

    def _parse_encoding_types(self) -> List[LDFEncodingType]:
        """Parse the ``Signal_encoding_types`` section."""
        types: List[LDFEncodingType] = []
        self._expect("{")
        while self._peek() != "}":
            if self._peek() is None:  # pragma: no cover - defensive EOF guard
                break
            enc_name = self._expect_identifier()
            self._expect("{")
            enc = LDFEncodingType(name=enc_name)
            while self._peek() != "}":
                if self._peek() is None:  # pragma: no cover - defensive EOF guard
                    break
                kind = self._consume()
                if kind == "logical_value":
                    self._expect(",")
                    val = self._consume_number()
                    self._expect(",")
                    text = self._strip_quotes(self._consume())
                    self._expect_semi()
                    enc.logical_values.append(LDFLogicalValue(signal_value=val, text=text))
                elif kind == "physical_value":
                    self._expect(",")
                    min_v = self._consume_number()
                    self._expect(",")
                    max_v = self._consume_number()
                    self._expect(",")
                    scale = self._consume_float()
                    self._expect(",")
                    offset = self._consume_float()
                    unit = ""
                    if self._peek() == ",":
                        self._consume()
                        unit = self._strip_quotes(self._consume())
                    self._expect_semi()
                    enc.physical_ranges.append(
                        LDFPhysicalRange(
                            min_value=min_v,
                            max_value=max_v,
                            scale=scale,
                            offset=offset,
                            unit=unit,
                        )
                    )
                elif kind == "bcd_value":
                    self._expect_semi()
                    enc.bcd = True
                elif kind == "ascii_value":
                    self._expect_semi()
                    enc.ascii = True
                else:
                    # skip unknown
                    while self._peek() not in (";", "}", None):
                        self._consume()
                    if self._peek() == ";":
                        self._consume()
            self._expect("}")
            types.append(enc)
        self._expect("}")
        return types

    def _parse_signal_representations(self) -> List[LDFSignalRepresentation]:
        """Parse the ``Signal_representation`` section."""
        reps: List[LDFSignalRepresentation] = []
        self._expect("{")
        while self._peek() != "}":
            if self._peek() is None:  # pragma: no cover - defensive EOF guard
                break
            enc_name = self._expect_identifier()
            self._expect(":")
            sigs: List[str] = []
            while self._peek() not in (";", "}", None):
                tok = self._consume()
                if tok == ",":
                    continue
                sigs.append(tok)
            self._expect_semi()
            reps.append(LDFSignalRepresentation(encoding_type=enc_name, signals=sigs))
        self._expect("}")
        return reps

    def _parse_node_attributes(self) -> List[LDFNodeAttributes]:
        """Parse the ``Node_attributes`` section."""
        attrs: List[LDFNodeAttributes] = []
        self._expect("{")
        while self._peek() != "}":
            if self._peek() is None:  # pragma: no cover - defensive EOF guard
                break
            node_name = self._expect_identifier()
            self._expect("{")
            na = LDFNodeAttributes(node_name=node_name)
            while self._peek() != "}":
                if self._peek() is None:  # pragma: no cover - defensive EOF guard
                    break
                key = self._consume()
                if key == "LIN_protocol":
                    self._expect("=")
                    na.lin_protocol = self._strip_quotes(self._consume())
                    self._expect_semi()
                elif key == "configured_NAD":
                    self._expect("=")
                    na.configured_nad = self._consume_number()
                    self._expect_semi()
                elif key == "initial_NAD":
                    self._expect("=")
                    na.initial_nad = self._consume_number()
                    self._expect_semi()
                elif key == "product_id":
                    self._expect("=")
                    na.product_id_supplier = self._consume_number()
                    self._expect(",")
                    na.product_id_function = self._consume_number()
                    self._expect(",")
                    na.product_id_variant = self._consume_number()
                    self._expect_semi()
                elif key == "response_error":
                    self._expect("=")
                    na.response_error = self._expect_identifier()
                    self._expect_semi()
                elif key == "P2_min":
                    self._expect("=")
                    na.p2_min = self._consume_float()
                    if self._peek() == "ms":
                        self._consume()
                    self._expect_semi()
                elif key == "ST_min":
                    self._expect("=")
                    na.st_min = self._consume_float()
                    if self._peek() == "ms":
                        self._consume()
                    self._expect_semi()
                elif key == "N_As_timeout":
                    self._expect("=")
                    na.n_as_timeout = self._consume_float()
                    if self._peek() == "ms":
                        self._consume()
                    self._expect_semi()
                elif key == "N_Cr_timeout":
                    self._expect("=")
                    na.n_cr_timeout = self._consume_float()
                    if self._peek() == "ms":
                        self._consume()
                    self._expect_semi()
                elif key == "configurable_frames":
                    self._expect("{")
                    while self._peek() != "}":
                        if self._peek() is None:  # pragma: no cover - defensive EOF guard
                            break
                        fname = self._consume()
                        if fname == ";":
                            continue
                        na.configurable_frames.append(fname)
                        if self._peek() == ";":
                            self._consume()
                    self._expect("}")
                else:
                    # unknown attribute — skip to semicolon
                    while self._peek() not in (";", "}", None):
                        self._consume()
                    if self._peek() == ";":
                        self._consume()
            self._expect("}")
            attrs.append(na)
        self._expect("}")
        return attrs

    def _skip_block(self) -> None:
        """Skip a balanced { … } block (already consumed the keyword before)."""
        self._expect("{")
        depth = 1
        while depth > 0 and self._peek() is not None:
            tok = self._consume()
            if tok == "{":
                depth += 1
            elif tok == "}":
                depth -= 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class LDFParseError(Exception):
    """Raised when an LDF file cannot be parsed."""


def parse_ldf(path: str) -> LDFFile:
    """Parse an LDF file and return an :class:`LDFFile` object.

    Args:
        path: Absolute or relative path to the ``.ldf`` file.

    Returns:
        A fully populated :class:`LDFFile` instance.

    Raises:
        FileNotFoundError: If *path* does not exist.
        LDFParseError: If the file contains a syntax error.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        content = fh.read()
    return parse_ldf_string(content)


def parse_ldf_string(content: str) -> LDFFile:
    """Parse LDF content from a string.

    Args:
        content: Full text of an LDF file.

    Returns:
        A fully populated :class:`LDFFile` instance.

    Raises:
        LDFParseError: If *content* contains a syntax error.
    """
    try:
        tokens = _tokenize(content)
        parser = _Parser(tokens)
        return parser.parse()
    except LDFParseError:
        raise
    except Exception as exc:
        raise LDFParseError(f"Unexpected parse error: {exc}") from exc
