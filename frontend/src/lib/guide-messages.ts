import type { GuideLanguage } from '@/lib/guide';

/**
 * The guide panel's own controls, in the language the guide is being heard in.
 *
 * Someone who chose Tamil because they do not read English cannot be expected
 * to find a button labelled "Resume", so the few words around the transcript
 * follow the transcript's language. The rest of the interface stays English.
 */
export interface GuideMessages {
  readonly eyebrow: string;
  readonly play: string;
  readonly pause: string;
  readonly resume: string;
  readonly part: (current: number, total: number) => string;
  readonly close: string;
  readonly chooseLanguage: string;
  readonly loading: string;
  readonly loadFailed: string;
  readonly voiceUnavailable: string;
  readonly clipFailed: string;
  readonly jumpHint: string;
}

export const GUIDE_MESSAGES: Readonly<Record<GuideLanguage, GuideMessages>> = {
  en: {
    eyebrow: 'Voice guide',
    play: 'Play the guide',
    pause: 'Pause',
    resume: 'Resume',
    part: (current, total) => `Part ${String(current)} of ${String(total)}`,
    close: 'Close the guide',
    chooseLanguage: 'Guide language',
    loading: 'Loading the guide',
    loadFailed: 'The guide could not be loaded',
    voiceUnavailable: 'Voice is not set up on this deployment. The whole guide is written below.',
    clipFailed: 'This part could not be played. The text below says the same thing.',
    jumpHint: 'Tap any part to hear it from there.',
  },
  hi: {
    eyebrow: 'आवाज़ गाइड',
    play: 'गाइड सुनें',
    pause: 'रोकें',
    resume: 'जारी रखें',
    part: (current, total) => `भाग ${String(current)} / ${String(total)}`,
    close: 'गाइड बंद करें',
    chooseLanguage: 'गाइड की भाषा',
    loading: 'गाइड लोड हो रही है',
    loadFailed: 'गाइड लोड नहीं हो सकी',
    voiceUnavailable: 'इस सर्वर पर आवाज़ चालू नहीं है। पूरी गाइड नीचे लिखी हुई है।',
    clipFailed: 'यह भाग चलाया नहीं जा सका। नीचे लिखा पाठ वही बात कहता है।',
    jumpHint: 'किसी भी भाग पर दबाएँ, वहीं से सुनाई देगा।',
  },
  ta: {
    eyebrow: 'குரல் வழிகாட்டி',
    play: 'வழிகாட்டியைக் கேளுங்கள்',
    pause: 'நிறுத்து',
    resume: 'தொடர்ந்து கேளுங்கள்',
    part: (current, total) => `பகுதி ${String(current)} / ${String(total)}`,
    close: 'வழிகாட்டியை மூடு',
    chooseLanguage: 'வழிகாட்டியின் மொழி',
    loading: 'வழிகாட்டி ஏற்றப்படுகிறது',
    loadFailed: 'வழிகாட்டியை ஏற்ற முடியவில்லை',
    voiceUnavailable:
      'இந்தத் தளத்தில் குரல் இயக்கப்படவில்லை. முழு வழிகாட்டியும் கீழே எழுத்தில் உள்ளது.',
    clipFailed: 'இந்தப் பகுதியை இயக்க முடியவில்லை. கீழே உள்ள எழுத்து அதையே சொல்கிறது.',
    jumpHint: 'எந்தப் பகுதியையும் தொட்டால், அங்கிருந்து கேட்கலாம்.',
  },
};
