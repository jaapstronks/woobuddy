# Changelog

## [0.2.0](https://github.com/jaapstronks/woobuddy/compare/v0.1.0...v0.2.0) (2026-09-08)


### Added

* **50:** frontend local-only review session + inline-redactions export ([#47](https://github.com/jaapstronks/woobuddy/issues/47)) ([d8bfd61](https://github.com/jaapstronks/woobuddy/commit/d8bfd6159ced13888cfa48193893eed0bfc42995))
* **analytics:** fire lead_captured Plausible event on form success ([#50](https://github.com/jaapstronks/woobuddy/issues/50)) ([47a0891](https://github.com/jaapstronks/woobuddy/commit/47a08911a31733d17ca3f12f4af1f8bb326244ff))
* **analyze:** anonymous mode for /api/analyze ([#50](https://github.com/jaapstronks/woobuddy/issues/50) phase 1) ([#46](https://github.com/jaapstronks/woobuddy/issues/46)) ([167f5ad](https://github.com/jaapstronks/woobuddy/commit/167f5adc97b0ebc215d6ddb9707f34eb03288b3a))
* **deploy:** report the running version in health, footer and deploy ([#128](https://github.com/jaapstronks/woobuddy/issues/128)) ([e408f9f](https://github.com/jaapstronks/woobuddy/commit/e408f9f4ad913ce83f060e534e7351bb66ecd8d0))
* **eval:** census of the corpus's logical structure and what redaction does to it ([#124](https://github.com/jaapstronks/woobuddy/issues/124)) ([361bc27](https://github.com/jaapstronks/woobuddy/commit/361bc278eabb4c6b11e3fec8dea259ac5abe479c))
* **eval:** detection evaluation harness over an ontlakt Woo corpus ([#120](https://github.com/jaapstronks/woobuddy/issues/120)) ([fc93b6a](https://github.com/jaapstronks/woobuddy/commit/fc93b6ad8be4f3b7d6ab1494fdb43320bae75cf9))
* **landing:** replace 'Open source' nav text and footer 'GitHub' text with icon ([#54](https://github.com/jaapstronks/woobuddy/issues/54)) ([242f18b](https://github.com/jaapstronks/woobuddy/commit/242f18b5a76cbcb089ab6a927a98eeb9d54eeb3c))
* **leads:** run the newsletter double opt-in from WOO Buddy itself ([70ed8a8](https://github.com/jaapstronks/woobuddy/commit/70ed8a8ba67043fe34efd78557bb7cbae8a21a7a))
* **onderbouwing:** tagged PDF + outlines for PDF/UA-1 accessibility ([#56](https://github.com/jaapstronks/woobuddy/issues/56)) ([ff6ac1d](https://github.com/jaapstronks/woobuddy/commit/ff6ac1df7d897b572734724e973d74f12d9a4bd4))
* **review:** onderbouwingsrapport export (audit log as Woo-besluit bijlage) ([#55](https://github.com/jaapstronks/woobuddy/issues/55)) ([b26899e](https://github.com/jaapstronks/woobuddy/commit/b26899eed15886bfae9982826a8e59c5018658b2))
* **review:** report detections that could not be placed on a page ([#111](https://github.com/jaapstronks/woobuddy/issues/111)) ([0b7067d](https://github.com/jaapstronks/woobuddy/commit/0b7067d75663ebe7a164e61a3e157c6fc20b4db3))
* **review:** shed toolbar labels on medium desktops to keep one row ([#62](https://github.com/jaapstronks/woobuddy/issues/62)) ([e645452](https://github.com/jaapstronks/woobuddy/commit/e64545247b2e9b4332a107e9c8e0b7de81c957fe))
* **review:** stack Tier 2 role picker vertically so labels never truncate ([#60](https://github.com/jaapstronks/woobuddy/issues/60)) ([d23d9e2](https://github.com/jaapstronks/woobuddy/commit/d23d9e2c408c2e7f67cc803a4635a59eac1ae553))
* **site:** /changelog with hand-written Dutch release notes ([#127](https://github.com/jaapstronks/woobuddy/issues/127)) ([198af19](https://github.com/jaapstronks/woobuddy/commit/198af192135a8127933fc2cc4c7bb674a30a4919))


### Fixed

* **backend:** pin the api image back to python 3.12 ([#102](https://github.com/jaapstronks/woobuddy/issues/102)) ([8caca52](https://github.com/jaapstronks/woobuddy/commit/8caca52f6d6e5bc94cc7aa080b38990591e3d0b1))
* **detection:** only count a postcode from the span onwards as address evidence ([#123](https://github.com/jaapstronks/woobuddy/issues/123)) ([450ccd1](https://github.com/jaapstronks/woobuddy/commit/450ccd1da14ab6e6fa2a1ddcde6880a1beffd5d4))
* **detection:** prefer false negatives over false positives in Tier 2 ([#119](https://github.com/jaapstronks/woobuddy/issues/119)) ([d0f5f45](https://github.com/jaapstronks/woobuddy/commit/d0f5f4594a54d1cf362907bb0c7e916684ea52d2))
* **detection:** read bestuursorganen and "namens dezen" as what they are ([#125](https://github.com/jaapstronks/woobuddy/issues/125)) ([f08a4f5](https://github.com/jaapstronks/woobuddy/commit/f08a4f595925b11e4084cce0cca422b3ae5aab40))
* **export:** drop PDF/A conversion, keep /Lang, run the chain off the event loop ([#110](https://github.com/jaapstronks/woobuddy/issues/110)) ([221c991](https://github.com/jaapstronks/woobuddy/commit/221c991b9de8eb1e5525c52756da2e7810f4475d))
* **frontend:** derive OCR assets during the image build ([#116](https://github.com/jaapstronks/woobuddy/issues/116)) ([0cd2c04](https://github.com/jaapstronks/woobuddy/commit/0cd2c04110a1b7a437950174312a74afb1a570d7))
* **landing:** drop Shoelace from SSR, Dutch errors, OneDrive CSP ([#68](https://github.com/jaapstronks/woobuddy/issues/68)) ([49cb23b](https://github.com/jaapstronks/woobuddy/commit/49cb23b1ac2902536fdbddab6ee35f4c719e819e))
* **leads:** repair the production contact form (Listmonk + Scaleway TEM) ([#100](https://github.com/jaapstronks/woobuddy/issues/100)) ([d45bafb](https://github.com/jaapstronks/woobuddy/commit/d45bafbb2f96591c9e25d9fefebde788cd06e138))
* **leads:** send lead mail from hallo@woobuddy.nl ([#106](https://github.com/jaapstronks/woobuddy/issues/106)) ([e380a0c](https://github.com/jaapstronks/woobuddy/commit/e380a0cfd139013dd94390cf2b3f31fa19216fb1))
* **pdf-extract:** break lines with a newline in extracted page text ([#122](https://github.com/jaapstronks/woobuddy/issues/122)) ([b3cb925](https://github.com/jaapstronks/woobuddy/commit/b3cb925855ef6380b15dcb0674272f84da597d64))
* **pdf-viewer:** set --total-scale-factor for the pdf.js 6 text layer ([#109](https://github.com/jaapstronks/woobuddy/issues/109)) ([8c7fa20](https://github.com/jaapstronks/woobuddy/commit/8c7fa207ab5e1ab24a6a74c392e91684005b1fe0))
* **pipeline:** occurrence-accurate bboxes and reported out-of-range redactions ([#107](https://github.com/jaapstronks/woobuddy/issues/107)) ([0a6745b](https://github.com/jaapstronks/woobuddy/commit/0a6745bff49ed27da9fb011a128a56265dde257f))
* **review:** make the unplaced-detections notice actionable ([#112](https://github.com/jaapstronks/woobuddy/issues/112)) ([9deafcd](https://github.com/jaapstronks/woobuddy/commit/9deafcd6c41e1ac563445634cc1a93a28a7a513b))
* **review:** narrow bboxes along the page's reading direction ([#115](https://github.com/jaapstronks/woobuddy/issues/115)) ([137979f](https://github.com/jaapstronks/woobuddy/commit/137979ff4d3f0d087e3cb76daf7bb13ea28f9ba9))
* **review:** narrow search-and-redact bboxes to the matched term ([#113](https://github.com/jaapstronks/woobuddy/issues/113)) ([96c669a](https://github.com/jaapstronks/woobuddy/commit/96c669ad55136ca13d8ff1c0be4836be60e4086f))
* **review:** put text bboxes in viewer space on rotated pages ([#114](https://github.com/jaapstronks/woobuddy/issues/114)) ([258c115](https://github.com/jaapstronks/woobuddy/commit/258c115103446783b8bdc3f08bcedbb7e2ef1f2e))
* **review:** undoable split/merge, persisted motivation, and export warnings ([#108](https://github.com/jaapstronks/woobuddy/issues/108)) ([c522b41](https://github.com/jaapstronks/woobuddy/commit/c522b4137b56d0061d8521a641b6ee7682ffe05c))
* **site:** date of the 0.2.0 release note ([#131](https://github.com/jaapstronks/woobuddy/issues/131)) ([0d03552](https://github.com/jaapstronks/woobuddy/commit/0d035529aa5d898e1bc4164d73ef97a37034c199))
* **tests:** accept rdf:Bag for dc:language under pikepdf 10.13 ([#121](https://github.com/jaapstronks/woobuddy/issues/121)) ([89fab3f](https://github.com/jaapstronks/woobuddy/commit/89fab3f754903c4552b1c591b89d321e23286e0d))
