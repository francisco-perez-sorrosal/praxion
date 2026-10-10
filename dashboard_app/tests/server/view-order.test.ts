import { describe, expect, it } from "vitest";

import { declaredViewIds, orderRenders } from "@/server/diagrams/view-order";

describe("declaredViewIds", () => {
  it("lists element, dynamic and deployment views in declaration order", () => {
    const source = [
      "views {",
      "  view index {",
      "    title 'System Context'",
      "  }",
      "  view components of praxion {",
      "    include *",
      "  }",
      "  dynamic view cis_loop_detail {",
      "    praxion -> developer 'reports'",
      "  }",
      "  deployment view production {",
      "    include *",
      "  }",
      "}"
    ].join("\n");

    expect(declaredViewIds(source)).toEqual([
      "index",
      "components",
      "cis_loop_detail",
      "production"
    ]);
  });

  it("keeps a repeated id at its first place and ignores the views block keyword", () => {
    const source = "views {\n  view b {\n  }\n  view a {\n  }\n  view b {\n  }\n}\n";

    expect(declaredViewIds(source)).toEqual(["b", "a"]);
  });

  it("declares nothing for a model without views", () => {
    expect(declaredViewIds("model {\n  praxion = system 'Praxion'\n}\n")).toEqual([]);
  });
});

describe("orderRenders", () => {
  const rendered = "/p/docs/diagrams/architecture/rendered";

  it("follows the declared view order within a rendered directory", () => {
    const paths = [`${rendered}/alpha.svg`, `${rendered}/beta.svg`, `${rendered}/index.svg`];
    const declared = new Map([[rendered, ["index", "beta", "alpha"]]]);

    expect(orderRenders(paths, declared)).toEqual([
      `${rendered}/index.svg`,
      `${rendered}/beta.svg`,
      `${rendered}/alpha.svg`
    ]);
  });

  it("places renders whose view is not declared after the declared ones, alphabetically", () => {
    const paths = [`${rendered}/zeta.svg`, `${rendered}/beta.svg`, `${rendered}/gamma.svg`];
    const declared = new Map([[rendered, ["beta"]]]);

    expect(orderRenders(paths, declared)).toEqual([
      `${rendered}/beta.svg`,
      `${rendered}/gamma.svg`,
      `${rendered}/zeta.svg`
    ]);
  });

  it("groups by rendered directory, directories alphabetically, undeclared directories too", () => {
    const concepts = "/p/docs/diagrams/concepts/rendered";
    const paths = [`${rendered}/b.svg`, `${concepts}/y.svg`, `${concepts}/x.svg`, `${rendered}/a.svg`];
    const declared = new Map([[rendered, ["b", "a"]]]);

    expect(orderRenders(paths, declared)).toEqual([
      `${rendered}/b.svg`,
      `${rendered}/a.svg`,
      `${concepts}/x.svg`,
      `${concepts}/y.svg`
    ]);
  });

  it("leaves the input untouched", () => {
    const paths = [`${rendered}/b.svg`, `${rendered}/a.svg`];

    orderRenders(paths, new Map([[rendered, ["b", "a"]]]));

    expect(paths).toEqual([`${rendered}/b.svg`, `${rendered}/a.svg`]);
  });
});
