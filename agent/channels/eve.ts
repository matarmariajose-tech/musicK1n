import { eveChannel } from "eve/channels/eve";
import { httpBasic, localDev, type AuthFn } from "eve/channels/auth";
const operator: AuthFn<Request> = async (request) => {
 const username = process.env.K1N_USERNAME;
 const password = process.env.K1N_PASSWORD;
 if (!username || !password) return null;
 return httpBasic({ username, password }, { realm: "K1N" })(request);
};
export default eveChannel({ auth: [operator, localDev()] });
