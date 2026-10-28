import {expect,it} from "vitest";
import {acknowledgementLanguage} from "./perception";
it.each(["uz","en","ru"] as const)("acknowledges in selected %s despite a different UI/conversation language", language=>{
 expect(acknowledgementLanguage(language,"ru","en")).toBe(language);
});
it("auto follows the actual conversation, then UI only if no language was heard",()=>{
 expect(acknowledgementLanguage("auto","ru","uz")).toBe("ru");
 expect(acknowledgementLanguage("auto",null,"uz")).toBe("uz");
});
