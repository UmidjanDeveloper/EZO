// Test fixture ONLY. Production examples never synthesize sensory events.
import * as sdk from '../../src/index';
(globalThis as unknown as {sdk:typeof sdk}).sdk=sdk;
