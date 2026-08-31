"""The allowlist IS the structure-only arm's scope statement.

Registered verbatim in preregistration.md A4.2 and disclosed to the attacker in
prompts/solution_blocks.md, because "what did you leave in?" is the first
question either result invites, and it should be answerable from a published
list rather than from an argument.

Governing principle, from A4.2: WHEN IN DOUBT, STRIP. Over-stripping narrows a
null result's scope but keeps it valid; under-stripping invalidates a positive
result, and the positive result is the one that re-scopes the project.
"""

GO_KEYWORDS = frozenset("""
break case chan const continue default defer else fallthrough for func go goto
if import interface map package range return select struct switch type var
""".split())

# Go predeclared identifiers (spec "Predeclared identifiers"), plus `main`.
# `main` is preserved because it is reserved by convention, marks an entrypoint
# (structure), and is identical across all six domains, so it discriminates
# nothing. `iota` does not occur in this corpus but belongs here on principle:
# it encodes "this is an enum," which is structure.
GO_PREDECLARED = frozenset("""
any bool byte comparable complex64 complex128 error float32 float64
int int8 int16 int32 int64 rune string uint uint8 uint16 uint32 uint64 uintptr
true false iota nil
append cap clear close complex copy delete imag len make max min new panic
print println real recover
main _
""".split())

# TS/JS ambient globals — never imported, so the import-binding rule cannot
# reach them. Deliberately minimal.
TS_GLOBALS = frozenset("""
undefined null true false NaN Infinity globalThis
console JSON Math Date Promise Object Array String Number Boolean Symbol BigInt
Error TypeError RangeError Map Set WeakMap WeakSet RegExp Function Proxy Reflect
fetch Request Response Headers RequestInit ResponseInit AbortController AbortSignal
URL URLSearchParams encodeURIComponent decodeURIComponent encodeURI decodeURI
setTimeout clearTimeout setInterval clearInterval queueMicrotask structuredClone
parseInt parseFloat isNaN isFinite window document navigator localStorage
any unknown never void object string number boolean bigint symbol readonly
Partial Required Readonly Record Pick Omit Exclude Extract NonNullable
ReturnType Parameters Awaited Array ReadonlyArray Iterable AsyncIterable
""".split())

# HTML intrinsic elements. `<table>` vs `<form>` is real structure and the set
# is closed platform vocabulary shared by every domain.
HTML_INTRINSICS = frozenset("""
a abbr address area article aside audio b base bdi bdo blockquote body br
button canvas caption cite code col colgroup data datalist dd del details dfn
dialog div dl dt em embed fieldset figcaption figure footer form h1 h2 h3 h4 h5
h6 head header hgroup hr html i iframe img input ins kbd label legend li link
main map mark menu meta meter nav noscript object ol optgroup option output p
param picture pre progress q rp rt ruby s samp script section select slot small
source span strong style sub summary sup table tbody td template textarea tfoot
th thead time title tr track u ul var video wbr svg path circle rect g line
polygon polyline text defs use
""".split())

# Standard attributes, preserved ONLY on an intrinsic element. The same word on
# an authored component (`<ReadDetail value={...}>`) is author-chosen and is
# canonicalised — that position-conditional rule is decidable only with the AST
# and is one of the concrete things the parser buys.
HTML_ATTRS = frozenset("""
id class className style title lang dir hidden tabIndex role key ref
href target rel download src alt width height loading srcSet sizes
type value defaultValue checked defaultChecked selected disabled readOnly
required placeholder name min max step pattern minLength maxLength multiple
autoComplete autoFocus form action method encType noValidate rows cols wrap
htmlFor colSpan rowSpan scope headers span start reversed open label
onClick onChange onInput onSubmit onReset onFocus onBlur onKeyDown onKeyUp
onKeyPress onMouseDown onMouseUp onMouseEnter onMouseLeave onMouseOver
onMouseOut onDoubleClick onContextMenu onScroll onWheel onDragStart onDrop
aria-label aria-labelledby aria-describedby aria-hidden aria-live aria-current
aria-expanded aria-controls aria-selected aria-disabled aria-invalid data-testid
""".split())

# Go stdlib top-level path segments. Anything whose first path segment is not
# here and contains no "." is treated as own-module and canonicalised.
GO_STDLIB_ROOTS = frozenset("""
archive bufio builtin bytes cmp compress container context crypto database
debug embed encoding errors expvar flag fmt go hash html image index io iter
log maps math mime net os path plugin reflect regexp runtime slices sort
strconv strings structs sync syscall testing text time unicode unsafe weak
""".split())
