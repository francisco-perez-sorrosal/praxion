# LikeC4 authoring recipes

DSL recipes for the pieces a diagram model is made of: the specification, elements, relationships, colour and
shape, views, view tags and dynamic views. The snippets build one small web-shop model, and together they
validate with the pinned toolchain (see [`render-and-regen.md`](render-and-regen.md)); a caveat worded
"before 1.59" names syntax an older local `likec4` rejects. Back to [`../SKILL.md`](../SKILL.md); the reasons behind the conventions are in
[`style-canon.md`](style-canon.md).

Contents: [Specification](#specification) · [Elements](#elements) · [Relationships](#relationships) ·
[Colour and shape](#colour-and-shape) · [Views and predicates](#views-and-predicates) ·
[View tags](#view-tags) · [Dynamic views](#dynamic-views) · [Icons](#icons) · [Version caveats](#version-caveats) ·
[Traps](#traps)

## Specification

Declare every kind, relationship kind, colour and tag once, in `_spec.c4`, and keep the model files free of
`specification` blocks. A kind that carries a `notation` has a category: the notation is the category name.

```likec4
specification {
  color brand #0A7C66

  element person {
    notation 'Person'
    style { shape person }
  }
  element system {
    notation 'System in scope'
    style { color brand }
  }
  element external {
    notation 'External system'
    style { color muted border dashed }
  }
  element container {
    notation 'Container'
  }
  element store {
    notation 'Data store'
    style { shape cylinder }
  }
  element component {
    style { shape rectangle }
  }

  relationship reads {
    title 'reads'
    line dashed
    color slate
  }

  tag c4_system_context
  tag c4_container
  tag deprecated
}
```

- A relationship kind takes its style properties directly, with no `style { }` wrapper; an element kind needs
  the wrapper.
- A kind with no `notation` (here `component`) gets its category per element, from metadata (next section).
- Tags that name a view's C4 type are declared here too; see [View tags](#view-tags).
- The legend LikeC4 draws in its own UI is built from the `notation` values, so a kit that sets them fills
  that legend for free.

## Elements

```likec4
model {
  customer = person 'Customer' {
    summary 'Orders goods and tracks parcels'
  }

  shop = system 'Web shop' {
    summary 'Sells goods and ships them'
    technology 'Python'

    web = container 'Storefront' {
      summary 'Renders the catalogue and takes orders'
      technology 'Python, FastAPI'
    }
    orders = container 'Order service' {
      summary 'Owns order state and payment status'
      technology 'Python'
    }
    db = store 'Order database' {
      summary 'Holds orders and customers'
      technology 'PostgreSQL'
    }
    audit = component 'Audit log' {
      #deprecated
      summary 'Records every order change'
      metadata { category 'Data store' owner 'orders-team' }
    }
  }

  mail = external 'Mail provider' {
    summary 'Delivers receipts and shipping notices'
  }
}
```

- Order inside the body: tags first, then `summary`, `description`, `technology`, `metadata` and `style`. A tag
  after another property is a parse error.
- `summary` is the short responsibility the diagram prints; `description` is the long text for LikeC4's detail
  panel. Give every element a `summary`. Inline form is `kind id 'Title' 'Summary' 'Technology'`; the nested form
  above reads better once an element has more than a title.
- `metadata { category '<name>' }` overrides the kind's notation when one kind spans several categories. Give an
  element exactly one: a second `category` line replaces the first in the export rather than adding to it, so a
  duplicate hides itself.
- Names are the names the code uses, so one rename in the model reaches every view.
- `extend <fqn> { ... }` adds children, tags or metadata to an element from another file without editing it.

## Relationships

```likec4
model {
  customer -> shop.web 'places an order through'
  shop.web -> shop.orders 'asks to create the order'
  shop.orders -> shop.audit 'records the change in'
  shop.orders -> mail 'sends the receipt through'
  shop.orders -[reads]-> shop.db 'reads order history from'
}
```

- The label states intent and reads as a sentence from source to target; never "uses" or "calls".
- `-[reads]->` selects the relationship kind. Use it for flows that only consume, so the legend can show
  read-only flows apart from writes.
- Declare a relationship once, at the level of its real endpoints; LikeC4 draws it at every ancestor level a
  view needs.
- One arrow points one way. When two elements exchange, write two relationships, each with its own intent,
  rather than one two-way line.

## Colour and shape

| Property | Values |
|---|---|
| `shape` | `rectangle` (default), `component`, `storage`, `cylinder`, `browser`, `mobile`, `person`, `queue`, `bucket`, `document` |
| `color` | theme names `primary` (default), `secondary`, `muted`, `slate`, `blue`, `indigo`, `sky`, `red`, `gray`, `green`, `amber`; or a custom name from `specification { color <name> <hex> }` |
| `border` | `dashed` (default), `dotted`, `solid`, `none`; on elements drawn as containers and on groups |
| `opacity` | a percentage, such as `15%`; low values make a frame recede behind its children |
| `size`, `padding`, `textSize` | `xsmall` to `xlarge` (`xs` to `xl`) |
| relationship `line`, `head`, `tail` | line `dashed` (default), `solid`, `dotted`; heads include `normal`, `onormal`, `diamond`, `odiamond`, `crow`, `vee`, `open`, `dot`, `odot`, `none` |

Precedence, low to high: project configuration defaults, the kind's `style`, the element's own `style`, view
rules in order, then `include ... with { }`, which always wins.

```likec4
views {
  view styled_containers of shop {
    #c4_container
    title 'Containers, restyled for review'
    include *
    style shop.orders { color red }                       // one element
    style element.tag = #deprecated { color muted }       // by tag
    include shop.web with { color sky }                   // wins over everything above
  }
}

global {
  style mute_deprecated element.tag = #deprecated {
    color muted
    opacity 40%
  }
}
```

A `global style` is applied by name inside a view (`global style mute_deprecated`) and keeps one treatment in
one place.

Two things this styling does not do. The committed renders draw each category from the regeneration command's
token table, not from `color`, `shape` or `line` in the model, so style the model for LikeC4's own views and
set the **category** for the renders. And LikeC4's own layout (`autoLayout`, `rank`) shapes only its own
views: the renders are laid out by the command's own engine, so a view that reads well in the LikeC4 UI has
still to pass the checks on its render.

## Views and predicates

```likec4
views {
  view landscape {
    #c4_system_context
    title 'Web shop and the people and systems around it'
    description 'Who uses the shop and what it depends on'
    include customer, shop, mail
  }

  view containers of shop {
    #c4_container
    title 'Containers inside the web shop'
    include *
    exclude element.tag = #deprecated
  }

  view orders_detail extends containers {
    title 'Order service and its neighbours'
    include shop.orders -> *
    include -> shop.orders
  }

  view framed of shop {
    #c4_container
    title 'Containers grouped by owner'
    include *
    group 'Order handling' {
      color amber
      border solid
      include shop.orders, shop.audit
    }
  }
}
```

| Predicate | Includes |
|---|---|
| `*` | In an unscoped view, the top-level elements; in a view `of X`, X and its children |
| `x.*` | The children of x |
| `x.**` | Every descendant of x that has a relationship in the view |
| `a -> b`, `-> x`, `x ->`, `-> x ->` | Relationships between, into, out of or through the named elements |
| `... where tag is #t`, `where kind is k`, `where metadata.k is "v"`, with `and`, `or`, `not` | A filtered selection |

- Scope a view with `of <element>`: `*` then means that element and its children, and the view becomes the
  click-through target for the element.
- A view's `title`, `description` and tag come before its predicates.
- `extends` inherits scope, rules and tags from the parent view, then applies its own.
- An element drawn together with its descendants becomes an enclosing frame, which is how a parent belongs in
  a view; a `group` is the same kind of frame with no model element behind it. Never draw an ancestor as a
  box beside its own descendants.
- Write the title as the subject in plain words. The title block adds the C4 type from the view's tag, so a
  title that repeats the type prints it twice.
- Fold detail rather than crowd a view: include `x.*` only where the children are the point, and let one
  element stand for a whole subsystem elsewhere.

## View tags

Every view that is not dynamic carries exactly one tag naming its C4 type, declared in the specification and
written first in the view body:

| Tag | Type printed in the title block |
|---|---|
| `c4_system_context` | System Context |
| `c4_system_landscape` | System Landscape |
| `c4_container` | Container |
| `c4_component` | Component |
| `c4_deployment` | Deployment |

A dynamic view needs no tag: the type is always Dynamic. A view that `extends` another inherits the parent's
tag, so tag it only when its type differs.

## Dynamic views

```likec4
views {
  dynamic view place_order {
    title 'A customer places an order'
    customer -> shop.web 'submits the basket'
    shop.web -> shop.orders 'asks to create the order' {
      notes 'The order service checks stock first'
    }
    shop.orders -> shop.db 'stores the order'
    parallel {
      shop.orders -> shop.audit 'records the order'
      shop.orders -> mail 'sends the receipt'
    }
    shop.orders -> shop.web 'confirms the order'
  }

  dynamic view pay {
    title 'Payment succeeds or is declined'
    customer -> shop.web 'submits payment details'
    shop.web -> shop.orders 'asks to charge the card'
    alt {
      when 'the card is accepted' {
        shop.orders -> shop.web 'confirms the payment'
      } else 'the card is declined' {
        shop.orders -> shop.web 'reports the decline'
      }
    }
  }
}
```

- Steps are numbered by order of appearance; there is no syntax to set a number. A step's `-[kind]->` selects
  its relationship kind, so a read-only step draws dashed.
- Use a dynamic view for one scenario whose order matters and is not obvious, and never to restate a static
  view. Keep it to the steps that tell the story.
- `variant sequence` draws the same steps as a sequence diagram and needs leaf elements only; `parallel { }`
  groups concurrent steps and cannot nest.
- `alt`, `opt`, `loop`, `break` and `try` flow control needs 1.59.0 or later.

## Icons

`icon tech:python` (or `tech:docker`, `tech:postgresql`) shows a bundled icon in LikeC4's own views. Verify any
name with `likec4 list-icons -g tech` before using it: names that look natural are often absent (`tech:gear`,
`tech:alert` and `tech:user` do not exist). The committed renders draw the person glyph only, so an icon never
substitutes for naming the technology in text.

## Version caveats

A project pinned to the toolchain in [`render-and-regen.md`](render-and-regen.md) can use all of this file. A
developer on an older local `likec4` meets these failures:

| Syntax | Needs |
|---|---|
| `multiple true` on a relationship kind or `with { }` | 1.57 |
| `title`, `technology` or tags on a relationship kind; `alt`, `opt`, `loop` in dynamic views | 1.59.0 |
| `<->`, view `order`, global predicates inside groups, `\/` in a view title | 1.59.3 |
| `export png --theme dark` taking effect | 1.59.3 (a silent no-op before) |

Before 1.59 a relationship kind accepts style properties only. The remedy is the pinned install, never a
rewrite of the model to the older syntax.

## Traps

- A tag colour set to a theme name is rejected on older versions; use a hex value.
- `rank same { ... }` across elements that sit in different groups failed layout on an older version; keep
  rank constraints inside one group, and re-check on the pinned version before relying on them.
- Set a `title` on every view: the title block prints it, and it is what the title check reads.
- A leftover element with no category draws as "Uncategorised" and fails the category check; run the command's
  `--check` after adding a kind.
- `preview-view` accepts element views only; check a dynamic view by regenerating.
