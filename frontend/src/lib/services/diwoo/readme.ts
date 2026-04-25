/**
 * Readme bundled inside the publication-export zip (#52). Dutch, plain
 * text — meant for the Woo-coordinator who unzips the bundle on the
 * publication side, not for the reviewer who produced it.
 */

import type { PublicationMetadataInput, PublicationContextRefs } from './types';

export function buildBundleReadme(
	input: PublicationMetadataInput,
	ctx: PublicationContextRefs,
	tooiSchemaVersion: string
): string {
	const lines: string[] = [];
	lines.push('WOO Buddy — publicatie-bundel');
	lines.push('===============================');
	lines.push('');
	lines.push(
		`Deze bundel bevat een gelakte PDF en bijbehorende publicatiemetadata,`
	);
	lines.push(
		`gegenereerd op ${ctx.exportedAt} volgens de DiWoo-standaard ` +
			`v${tooiSchemaVersion} (https://standaarden.overheid.nl/diwoo/metadata).`
	);
	lines.push('');
	lines.push('Inhoud van de zip:');
	lines.push('------------------');
	lines.push(`  redacted.pdf       — De gelakte PDF (oorspronkelijke bestand: ${input.bestandsnaam}).`);
	lines.push('  metadata.xml       — DiWoo-metadata, geldig volgens diwoo:Document/DiWoo (v0.9.8).');
	lines.push('  metadata.json      — Dezelfde gegevens in GPP-Woo publicatiebank-formaat.');
	lines.push('                       Bevat een publicatie-envelop en het bijbehorende document.');
	lines.push('  redaction-log.csv  — Lakkenoverzicht: per gelakte passage de Woo-grond, het type,');
	lines.push('                       de tier en de beoordelingsstatus. Bevat geen tekstinhoud.');
	lines.push('  README.txt         — Dit bestand.');
	lines.push('');
	lines.push('Wat doet u hiermee?');
	lines.push('-------------------');
	lines.push('Voer de bundel in uw publicatieplatform in:');
	lines.push('  • GPP-publicatiebank (open source) — gebruik metadata.json + redacted.pdf.');
	lines.push('    Documentatie: https://github.com/GPP-Woo/GPP-publicatiebank');
	lines.push('  • Een ander Woo-platform dat DiWoo-metadata leest —');
	lines.push('    gebruik metadata.xml + redacted.pdf.');
	lines.push('  • Eigen documentmanagementsysteem — sla metadata.xml op naast de PDF en');
	lines.push('    gebruik redaction-log.csv als bijlage bij het Woo-besluit.');
	lines.push('');
	lines.push('Belangrijke aandachtspunten');
	lines.push('---------------------------');
	lines.push('  • De gelakte PDF is onomkeerbaar — de oorspronkelijke tekst staat');
	lines.push('    niet meer in het bestand. Bewaar uw eigen werkkopie van het origineel.');
	lines.push('  • De CSV bevat geen tekstinhoud (client-first architectuur). De server');
	lines.push('    van WOO Buddy heeft de inhoud van uw document nooit opgeslagen.');
	lines.push('  • Controleer voor publicatie of de identifier en informatiecategorie');
	lines.push('    overeenkomen met uw eigen registratie. metadata.xml is een goede');
	lines.push('    startwaarde, geen vervanging voor uw zaaksysteem.');
	lines.push('');
	lines.push('Vragen of fouten in de metadata?');
	lines.push('  https://woobuddy.nl/contact');
	lines.push('');
	return lines.join('\n');
}
