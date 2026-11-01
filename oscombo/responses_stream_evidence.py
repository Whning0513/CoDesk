"""Passive, bounded terminal-event observation for Responses API streams.

No content leaves this object. Parsing failures affect evidence only, never
forwarding. SSE framing supports CR, LF, CRLF, and multiple data lines.
"""
from __future__ import annotations

import codecs
import json


class ResponseEvidence:
    LIMIT = 4 * 1024 * 1024

    def __init__(self, content_type: str):
        mime = content_type.split(';', 1)[0].strip().lower()
        self.format = 'sse' if mime == 'text/event-stream' else 'json' if mime == 'application/json' else 'unknown'
        self.invalid = False
        self.terminal = None
        self.done = False
        self.buffer = ''
        self.data = []
        self.event = None
        self.decoder = codecs.getincrementaldecoder('utf-8')('strict')

    def feed(self, chunk: bytes) -> None:
        if self.invalid or self.format == 'unknown':
            return
        try:
            self.buffer += self.decoder.decode(chunk)
            if len(self.buffer) + sum(len(x) for x in self.data) > self.LIMIT:
                self.invalid = True
                return
            if self.format == 'sse':
                self._lines(False)
        except (UnicodeError, ValueError, TypeError):
            self.invalid = True

    def _lines(self, final: bool) -> None:
        while self.buffer:
            i = next((j for j, ch in enumerate(self.buffer) if ch in '\r\n'), -1)
            if i < 0:
                return
            if self.buffer[i] == '\r' and i + 1 == len(self.buffer) and not final:
                return
            step = 2 if self.buffer[i:i+2] == '\r\n' else 1
            line, self.buffer = self.buffer[:i], self.buffer[i+step:]
            if not line:
                self._dispatch()
            elif line.startswith(':'):
                continue
            else:
                field, sep, value = line.partition(':')
                if sep and value.startswith(' '):
                    value = value[1:]
                if field == 'data':
                    self.data.append(value)
                elif field == 'event':
                    self.event = value

    def _dispatch(self) -> None:
        if not self.data:
            self.event = None
            return
        text = '\n'.join(self.data)
        name = self.event
        self.data, self.event = [], None
        if text == '[DONE]':
            if self.done:
                self.invalid = True
            self.done = True
            return
        if self.done or self.terminal is not None:
            self.invalid = True
            return
        try:
            item = json.loads(text)
        except (ValueError, TypeError):
            self.invalid = True
            return
        if not isinstance(item, dict) or not isinstance(item.get('type'), str):
            self.invalid = True
            return
        kind = item['type']
        if name and name != kind:
            self.invalid = True
            return
        if kind in {'response.completed', 'response.failed', 'response.incomplete', 'error'}:
            if self.terminal is not None:
                self.invalid = True
            self.terminal = kind

    def finish(self) -> dict:
        if not self.invalid and self.format != 'unknown':
            try:
                self.buffer += self.decoder.decode(b'', final=True)
                if self.format == 'sse':
                    self._lines(True)
                    # A nonempty unfinished line or un-dispatched event means
                    # the last frame was not completed on the wire.
                    if self.buffer or self.data or self.event:
                        self.invalid = True
                else:
                    item = json.loads(self.buffer)
                    if not isinstance(item, dict) or item.get('object') != 'response':
                        self.invalid = True
                    elif item.get('status') in {'completed', 'failed', 'incomplete'}:
                        self.terminal = 'response.' + item['status']
            except (UnicodeError, ValueError, TypeError):
                self.invalid = True
        terminal = ('malformed' if self.invalid else self.terminal or
                    ('done_only' if self.done else 'missing'))
        return {'response_format': self.format, 'response_terminal': terminal,
                'response_evidence_version': 1}
