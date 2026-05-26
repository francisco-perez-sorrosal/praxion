# Vue 3 Context

Vue 3 Composition API + Nuxt 3 patterns layered on top of the TypeScript baseline. Back to [SKILL.md](../SKILL.md).

Load [`contexts/typescript.md`](typescript.md) first — this file layers Vue-specific patterns on top and does not restate pnpm/volta setup, tsconfig configuration, or Vitest baseline.

## Contents

- [Scaffolding](#scaffolding)
- [Code quality toolchain — ESLint path](#code-quality-toolchain--eslint-path)
- [Type checking — vue-tsc](#type-checking--vue-tsc)
- [Composition API with script setup](#composition-api-with-script-setup)
- [Testing with @vue/test-utils + Vitest](#testing-with-vuetest-utils--vitest)
- [Nuxt 3 setup conventions](#nuxt-3-setup-conventions)

## Scaffolding

```bash
npm create vue@latest
```

The `create-vue` wizard (official Vue scaffolding tool) prompts for:
- TypeScript support (select Yes)
- Vue Router, Pinia, Vitest, Playwright, ESLint+Prettier

For Nuxt 3:

```bash
pnpm dlx nuxi@latest init my-app
cd my-app
pnpm install
```

---

## Code quality toolchain — ESLint path

Vue projects use ESLint + `eslint-plugin-vue` + Prettier. Biome v2 does not support
`eslint-plugin-vue`, so the Biome default from `contexts/typescript.md` does **not** apply
to Vue projects. This is the framework-plugin necessity, not a preference.

Install:

```bash
pnpm add -D eslint @eslint/js typescript-eslint eslint-plugin-vue vue-eslint-parser prettier eslint-config-prettier
```

Minimal `eslint.config.mjs` (flat config) for Vue + TypeScript:

```js
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import pluginVue from "eslint-plugin-vue";
import vueParser from "vue-eslint-parser";
import prettierConfig from "eslint-config-prettier";

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs["flat/recommended"],
  prettierConfig,
  {
    files: ["**/*.vue"],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tseslint.parser,
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
        extraFileExtensions: [".vue"],
      },
    },
  },
);
```

CI steps:

```bash
pnpm prettier --check .
pnpm eslint .
```

Fix mode (local):

```bash
pnpm prettier --write .
pnpm eslint --fix .
```

**Gotchas**:
- `vue-eslint-parser` must be the outer parser; `@typescript-eslint/parser` is set as the
  inner parser via `parserOptions.parser`. Reversing them breaks Vue SFC parsing.
- `eslint-plugin-vue` v9+ ships flat-config presets (`flat/recommended`, `flat/vue3-essential`,
  etc.). Do not use the legacy object-style config in new projects.
- `tseslint.configs.strictTypeChecked` adds type-aware rules that slow lint significantly on
  Vue projects due to `.vue` file processing. Start with `tseslint.configs.recommended` and
  upgrade after measuring.

---

## Type checking — `vue-tsc`

`vue-tsc` wraps `tsc` with `.vue` SFC awareness. Use it instead of bare `tsc --noEmit` for
Vue projects.

Install:

```bash
pnpm add -D vue-tsc
```

`package.json` scripts:

```json
{
  "scripts": {
    "typecheck": "vue-tsc --noEmit",
    "typecheck:watch": "vue-tsc --noEmit --watch"
  }
}
```

`tsconfig.json` additions for Vue SFCs:

```json
{
  "extends": "@tsconfig/strictest/tsconfig.json",
  "compilerOptions": {
    "target": "ESNext",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "lib": ["ESNext", "DOM", "DOM.Iterable"],
    "jsx": "preserve",
    "jsxImportSource": "vue"
  },
  "include": ["src/**/*", "src/**/*.vue"],
  "exclude": ["node_modules", "dist"]
}
```

**Gotchas**:
- `vue-tsc` and `tsc` use separate processes; running both is redundant. Use `vue-tsc --noEmit`
  as the single type-checking gate for Vue projects.
- `moduleResolution: "Bundler"` is required for Vite + Vue; `"NodeNext"` causes spurious
  `.js` extension resolution errors on `.vue` imports.
- Volar (Vue Language Tools VSCode extension) must be enabled; Vetur is deprecated for Vue 3.

---

## Composition API with `<script setup>`

`<script setup>` is the current best practice for Vue 3 components. It is a compile-time
syntax sugar over the Composition API that removes boilerplate.

```vue
<script setup lang="ts">
import { ref, computed } from "vue";

interface Props {
  title: string;
  count?: number;
}

const props = withDefaults(defineProps<Props>(), {
  count: 0,
});

const emit = defineEmits<{
  increment: [amount: number];
}>();

const doubled = computed(() => props.count * 2);

function handleClick(): void {
  emit("increment", 1);
}
</script>

<template>
  <div>
    <h1>{{ props.title }}</h1>
    <p>Count: {{ props.count }} | Doubled: {{ doubled }}</p>
    <button @click="handleClick">Increment</button>
  </div>
</template>
```

Key patterns:
- `defineProps<T>()` and `defineEmits<T>()` with TypeScript generics — no runtime declaration object
- `withDefaults` for default prop values
- Named emit tuple syntax: `{ eventName: [arg1Type, arg2Type] }`
- `ref<T>()` for mutable reactive values; `computed()` for derived state
- `reactive()` for objects when destructuring is not needed; prefer `ref` + `.value` otherwise

### Composables

Extract reusable stateful logic into composables (by convention: `use` prefix, `src/composables/`):

```ts
// src/composables/useCounter.ts
import { ref } from "vue";

export function useCounter(initial = 0) {
  const count = ref(initial);
  function increment(): void {
    count.value++;
  }
  return { count, increment } as const;
}
```

---

## Testing with `@vue/test-utils` + Vitest

`@vue/test-utils` is the official Vue testing library. It integrates with Vitest via
the `@vitejs/plugin-vue` transform.

Install:

```bash
pnpm add -D @vue/test-utils @vitejs/plugin-vue jsdom
```

`vitest.config.ts` for Vue SFC support:

```ts
import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: "jsdom",
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
    },
  },
});
```

Component test example:

```ts
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import MyComponent from "./MyComponent.vue";

describe("MyComponent", () => {
  it("renders title prop", () => {
    const wrapper = mount(MyComponent, {
      props: { title: "Hello Vue", count: 3 },
    });
    expect(wrapper.find("h1").text()).toBe("Hello Vue");
  });

  it("emits increment on button click", async () => {
    const wrapper = mount(MyComponent, {
      props: { title: "Test", count: 0 },
    });
    await wrapper.find("button").trigger("click");
    expect(wrapper.emitted("increment")).toEqual([[1]]);
  });
});
```

**Gotchas**:
- `mount` renders the component in the jsdom environment. For Teleport, Suspense, or
  browser-specific behavior, use Playwright for E2E tests instead.
- `@vue/test-utils` v2 is for Vue 3; v1 is for Vue 2. Do not mix.
- Async operations (e.g., `nextTick`) require `await` in tests:
  `await wrapper.trigger("click")` or `await nextTick()`.

---

## Nuxt 3 setup conventions

Nuxt 3 is a meta-framework over Vue 3 and provides auto-imports, file-based routing,
and server routes.

### Auto-imports

Nuxt 3 auto-imports Vue Composition API functions (`ref`, `computed`, etc.), Nuxt
composables (`useFetch`, `useRoute`, `useRuntimeConfig`), and components from `components/`.
No manual import statements needed for these in `.vue` files.

```vue
<script setup lang="ts">
// No explicit imports needed for ref, computed, useFetch, useRoute
const route = useRoute();
const { data } = await useFetch("/api/items");
const count = ref(0);
</script>
```

To get TypeScript auto-import types in editor and `vue-tsc`, run:

```bash
pnpm nuxi prepare
```

This generates `.nuxt/` type declarations. Add `.nuxt/` to `.gitignore`; commit only the
`nuxt.config.ts`.

### File-based routing

```
pages/
  index.vue          → /
  about.vue          → /about
  users/
    index.vue        → /users
    [id].vue         → /users/:id
```

Dynamic segment syntax: `[param].vue`. Catch-all: `[...slug].vue`.

Access route params:

```vue
<script setup lang="ts">
const route = useRoute();
const id = route.params.id as string;
</script>
```

### Server routes

Place files under `server/api/` or `server/routes/` for backend endpoints:

```ts
// server/api/items.get.ts
export default defineEventHandler(async () => {
  return [{ id: 1, name: "Item 1" }];
});
```

Method suffix: `.get.ts`, `.post.ts`, `.delete.ts`. Access from the Vue side:

```vue
<script setup lang="ts">
interface Item { id: number; name: string }
const { data } = await useFetch<Item[]>("/api/items");
</script>
```

### `nuxt.config.ts` baseline

```ts
export default defineNuxtConfig({
  devtools: { enabled: true },
  typescript: {
    strict: true,
    typeCheck: true,   // runs vue-tsc during build
  },
  modules: [],
});
```

Setting `typescript.typeCheck: true` runs `vue-tsc` during `nuxt build`. In CI, also
run `pnpm nuxi typecheck` as a separate gate (faster feedback than waiting for build).

**Gotchas**:
- Nuxt 3 auto-imports can cause TypeScript errors until `.nuxt/` types are generated.
  Always run `pnpm nuxi prepare` after adding a new module or changing composables.
- SSR is on by default. If you do not need SSR, set `ssr: false` in `nuxt.config.ts` to
  avoid hydration-related issues during development.
- `useFetch` returns a reactive ref; `data.value` is the actual payload. Destructuring
  `const { data }` gives the ref — access payload as `data.value`, not `data`.
