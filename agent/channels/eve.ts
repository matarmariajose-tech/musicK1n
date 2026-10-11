import { eveChannel } from 'eve/channels/eve';
import { operator } from '../lib/auth.js';
export default eveChannel({auth:operator});
