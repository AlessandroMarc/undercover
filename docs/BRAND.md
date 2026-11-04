Brand guide: claims dashboard
4 nov 2026 · @Alessandro
The claims dashboard should feel calm, clear and quick to scan: every claim shows where it stands and what happens next.
Principles
1. Status first. The state of a claim is the first thing a person sees, shown by color, an icon and a label together.
2. Numbers are the content. Amounts, dates and counts get the most space and a fixed, aligned format.
3. Color carries meaning. Brand colors mark states and chart series. They are not decoration.
4. Quiet surfaces. Panels separate by tone and spacing, not by lines, so the data stands out.
Typography
All three fonts come from Google Fonts. Each has one job, so a person can tell what a piece of text is before reading it.
Role
Font
Used for
Headings, body, labels
Instrument Sans (400, 500, 600)
Page titles, panel titles, table text, buttons, form labels
Accent
Instrument Serif (regular, italic)
One tagline or quote per screen, such as a welcome line or an empty state
Numbers and identifiers
JetBrains Mono (400, 500)
Amounts, dates, counts, claim IDs, policy numbers, code
Size scale
Style
Font
Size / line height
Weight
Page title
Instrument Sans
28 / 36 px
600
Panel title
Instrument Sans
18 / 24 px
600
Body
Instrument Sans
14 / 20 px
400
Label
Instrument Sans
12 / 16 px
500
Key figure
JetBrains Mono
32 / 40 px
500
Table figure
JetBrains Mono
13 / 20 px
400
Accent
Instrument Serif
24 / 32 px
Regular
Rules
• Never set text below 12 px.
• Turn on tabular figures for every number so digits line up in columns. Right-align number columns.
• Use sentence case everywhere, including buttons and column headers.
• Keep Instrument Serif out of tables, charts and forms. It is for one short line, not for data.
Color palette
Five brand colors, plus two inks for text. Contrast ratios are approximate, measured against WCAG 2.2.
Color
Hex
Text on it
Contrast
Use
Sea Green
#06D6A0
Midnight
6.4 : 1
Primary actions, positive states, the first chart series
Marigold
#FFC145
Midnight
7.5 : 1
Secondary actions, states that are waiting, the second series
Coral
#F78C6B
Midnight
5.1 : 1
Tertiary actions, states that need attention, the third series
Cerulean
#118AB2
White
4.0 : 1
Information, links, the fourth series
Raspberry
#EF476F
White
3.6 : 1
Alerts and highlights, the fifth series
Midnight
#073B4C
n/a
12 : 1 on white
Ink on light backgrounds
Sea Mist
#CDD8DB
n/a
11 : 1 on #04232E
Ink on dark backgrounds
White text on Cerulean and Raspberry is below 4.5 : 1. On the bright brand fill, use that pairing only for text of 18 px bold or larger. For buttons, badges and any smaller white text, use the deeper fills in the next section.
Use one primary action per panel. Marigold and Coral are for secondary and tertiary actions, never for two competing buttons of equal weight.
Readable text colors
Bright brand colors fail as small text on white. Use these variants whenever a brand color colors text, an icon next to text, or a small badge.
Color
Text on light
Contrast on white
Text on dark
Contrast on black
Sea Green
#057A5E
5.3 : 1
#06D6A0 (unchanged)
11 : 1
Marigold
#946200
5.1 : 1
#FFC145 (unchanged)
13 : 1
Coral
#B83F22
5.5 : 1
#F78C6B (unchanged)
8.9 : 1
Cerulean
#0E6F8F
5.7 : 1
#4DB8DE
9.2 : 1
Raspberry
#C21B46
5.9 : 1
#FF7A97
8.5 : 1
• On the light page background #F0F4F5, every light-mode variant stays above 4.5 : 1.
• Sea Green, Marigold and Coral are already bright enough on dark panels, so they stay as they are. Only Cerulean and Raspberry are lightened.
• Fills with white text: use the light-mode variant of Cerulean (#0E6F8F) or Raspberry (#C21B46) as the fill. Fills in Sea Green, Marigold and Coral keep Midnight text.
• Body text is always Midnight on light and Sea Mist on dark. Color is for status and emphasis, not for paragraphs.
Claim status and charts
Colors are assigned in a fixed order: Sea Green, Marigold and Coral when three items sit side by side, then Cerulean fourth and Raspberry fifth. The same order applies to claim states and to chart series.
Claim state
Color
Icon
Label
Approved
Sea Green
Check
Approved
In review
Marigold
Clock
In review
Needs info
Coral
Question mark
Needs info
New
Cerulean
Dot
New
Denied or overdue
Raspberry
Flag
Denied, Overdue
Status badge
• A rounded pill with an icon and a short label. Never color alone.
• Fill is a flat 16% tint of the state color. Text and icon use the readable text variant for the current mode.
• Keep the label to one or two words.
Charts
• Use at most five series. Past five, group the smallest into Other and show it in Sea Mist or Midnight at 40% opacity.
• Label series directly on the chart when there is room. Otherwise add a legend with the series name next to each swatch.
• Separate touching bars and slices with a 2 px gap in the surface color, not a line.
• Show the value in JetBrains Mono. Round to whole dollars on charts, and show cents in tables.
• Fill areas under lines with a flat 12% tint, not a gradient.
• Raspberry is reserved for the one thing that needs action. If everything is highlighted, nothing is.
Surfaces and shape
Panels are rounded and have no outline. Layers are told apart by tone and spacing.
Element
Light mode
Dark mode
Page background
#F0F4F5
#04232E
Panels and cards
#FFFFFF
#000000
Nested cards inside a panel
#F0F4F5 (the page color)
#04232E (the page color)
Main text
Midnight #073B4C
Sea Mist #CDD8DB
Secondary text
#456C79 (5.7 : 1 on white)
#8F9799 (7 : 1 on black)
Shape and spacing
Item
Value
Panel radius
16 px
Nested card and input radius
12 px
Button radius
12 px
Badge radius
Fully round
Panel padding
24 px
Gap between panels
16 px
Spacing grid
8 px steps (4 px for tight icon gaps)
Table row height
48 px
Rules
• Panels have no outline, no one-sided border and no thin line across the top of the page. The page header sits on the page background.
• In dark mode, black panels sit slightly darker than the page. Keep the 16 px gap and never nest more than two levels.
• Separate table rows with height and a hover tint, not dividing lines.
• Keyboard focus is the one exception to the no-outline rule: show a 2 px ring in the Cerulean text variant, offset 2 px, on every interactive element.
• Use shadows only for menus and dialogs, and only in light mode. In dark mode, dim the page behind a dialog instead.
Numbers and money
All numbers and identifiers use JetBrains Mono with tabular figures, right-aligned in columns.
Item
Rule
Example
Money
US dollars, dollar sign, thousands separator, always two decimals in tables and detail views
$1,250.00
Negative money
True minus sign before the dollar sign
−$1,250.00
Zero
Show it, do not leave it blank
$0.00
Chart axes
Drop cents and abbreviate above $9,999. The tooltip shows the full amount
$250K, $1.2M
Dates
Month, day, year
Nov 4, 2026
Date and time
12-hour clock, local time
Nov 4, 2026, 2:30 PM
Recent activity
Relative time for the last 7 days, exact date on hover
2 days ago
Percentages
Whole numbers, one decimal under 10%
92%, 4.5%
Counts
Thousands separator, with the noun
1,204 claims
Claim IDs
Never shortened. Include a copy button
CLM-482913
Do not add the currency code to amounts. Add it to a column header only if a view ever mixes currencies.
Avoid
Avoid
Why
Do this instead
A border or stripe on one edge of a panel, card or row
It reads as a template pattern and adds noise
Use a status badge, or a tone change across the whole card
Thin lines across the top of the page, such as a header rule
It splits the page and competes with the data
Let the header sit on the page background
Gradient fills
They blur the data and clash with flat panels
Use flat color or a flat tint
Color as the only signal for a state
Some people cannot tell the colors apart
Pair color with an icon and a label
Bright Sea Green or Marigold as small text on light backgrounds
Contrast is under 2 : 1
Use the readable text variants
Small white text on bright Cerulean or Raspberry
Contrast is under 4.5 : 1
Use the deeper fills from Readable text colors
More than five colors in one chart
Series become hard to tell apart
Group the smallest into Other
All caps labels
They slow reading
Use sentence case
Outlined panels
They add visual weight with no gain
Use tone and spacing
Tone
Write in plain business English with US spelling, as a clear colleague would.
• Labels are one to three words. Buttons start with a verb.
• Use everyday words. Say "use", not "utilize", and "pay", not "disburse".
• Never use exclamation marks.
• Errors and empty states say what happened and what to do next, in two short sentences or fewer.
• Use sentence case and US spelling: color, center, canceled, organization.
• Money is in US dollars, such as $1,250.00.
Instead of
Write
Adjudication pending
In review
Submit claim now!
Submit claim
Something went wrong!
We could not save your changes. Try again.
No data to display
No claims match these filters. Clear filters to see all claims.
Claim approved in the amount of USD 1250
Approved for $1,250.00
Remit indemnity disbursement
Pay claim
Colour legend
Color legend
The accent font may carry one short line, such as a welcome message: Here is where your claims stand today.