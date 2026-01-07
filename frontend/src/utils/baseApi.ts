const BaseUrl = "http://localhost:8000/api/v1/";
export async function baseApi(urlPart: string, init?: RequestInit): Promise<any> {

    // return {
    //     message: "Hi I am API"
    // }

  try {
    // debugger;
    const url = BaseUrl + urlPart;
    const headers: HeadersInit = {
      "Content-Type": "application/json",
    };
    if (init == undefined) {
      init = {
        headers: headers,
      };
    } else if (init.headers == undefined) {
      init = { ...init, headers: headers, };
    } 
    const res = await fetch(url, init);
   
    if (res.ok) {
      const data = await res.json();
      return data;
    }
    const text = await res.text();
    let jsonText: undefined | string;
    try {
      jsonText = JSON.parse(text);
    } catch {
      throw new Error(text);
    }
    throw new Error(jsonText);
  } catch (err) {
    if (err instanceof Error) {
      throw new Error(err.message);
    }
    throw new Error("Server Error.");
  } 
}
