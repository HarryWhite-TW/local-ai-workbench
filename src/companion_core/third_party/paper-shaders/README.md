# Paper Shaders 0.0.82

This candidate uses a locally bundled subset of the official zero-dependency
`@paper-design/shaders` package. The npm tarball was verified against:

    sha512-eCxYQrrCxRVc4KG8sLSQecsq8Ymstbaq/FqZjq/fhOa6UiR1ZZfdMO5IJpHmwL0GYmfzvZVQ4l8ZOLux0uLVdg==

Source: https://registry.npmjs.org/@paper-design/shaders/-/shaders-0.0.82.tgz
Project: https://github.com/paper-design/shaders
License and notices are preserved alongside this file.

The source adapter in this directory calls Paper's ShaderMount with the official
Liquid Metal shader and built-in diamond geometry. It passes local values and no
images or other third-party assets. To rebuild, resolve the adapter's import
from the exact npm tarball (extracted as `package/`), then bundle as ESM with
esbuild 0.28.2 using `--bundle --format=esm --legal-comments=inline`.
esbuild is a build tool only. Runtime serves the resulting trace-liquid-metal.js
from the existing local static allowlist under the same CSP.

