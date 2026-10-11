import { httpBasic, type AuthFn } from 'eve/channels/auth';
export const operator: AuthFn<Request> = async request => {
 const username=process.env.K1N_USERNAME,password=process.env.K1N_PASSWORD;
 if (!username || !password) return null;
 return httpBasic({username,password},{realm:'K1N'})(request);
};
