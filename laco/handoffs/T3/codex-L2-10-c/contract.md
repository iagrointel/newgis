# Contract extension (41 functions total)
Existing 18 names/scalar behavior retained. New functions case sensitive. Text indices/counts use Unicode code points, zero based, nonnegative integers; invalid index/count => tipo_invalido. New strict functions propagate null if any argument is null except Lista, Obter, Contem, Decode. Strict wrong type => tipo_invalido.
- Trim(text): trim only ASCII whitespace space/tab/CR/LF/formfeed/vertical tab.
- Left(text,count), Right(text,count): first/last count code points (zero => empty).
- Mid(text,start,count?): slice from start for count points, omitted count to end.
- Find(needle,text,start=0): first code-point index at/after start; -1 missing.
- Split(text,separator): literal splitting; empty separator => code points; empty text/nonempty separator => [''].
- Replace(text,old,new): replace all literal occurrences; empty old => original text.
- Floor(number), Ceil(number), Sqrt(number): ordinary math; negative sqrt => numero_invalido.
- Weekday(epoch_ms): UTC Sunday=0 through Saturday=6; supported date range year 1..9999.
- Decode(value, match, result, ..., default): even arity >=4; lazy value/matches and chosen result/default only; strict deep JSON equality (bool != number; object key order ignored).
- Lista(...): 0..64 args, including null; new list.
- Contagem(list or text or dictionary): length (code points for text, own keys for dict).
- Primeiro(list), Ultimo(list): element or null if empty.
- Obter(list,index,default?), Obter(dictionary,key,default?): index nonnegative integer, key string; missing => default or null; default eagerly evaluated; null container => default/null. Forbidden keys __proto__, prototype, constructor => campo_nao_permitido.
- Contem(list,value): strict deep equality; null value permitted; null list => null.
- Soma(list), Media(list): finite numbers only; empty => 0 / null; null member => null.
- Reverter(list): copied reversed list.
- Unicos(list): first occurrence order; strict deep equality.
- Juntar(list,separator=''): scalar values use Texto rules, null => ''; collection members => tipo_invalido.
Bounds: MAX_COLECAO=1024 per container; MAX_VALOR_NOS=4096 aggregate per value; MAX_VALOR_TEXTO=20000 cumulative code points per value; MAX_VALOR_PROFUNDIDADE=20. Invalid/non-JSON/cyclic values => tipo_invalido or valor_grande when depth/size exceeded; nonfinite number => numero_invalido. Every visited value and collection operation charged to evaluation steps, clock checked each step. Intermediate results bounded. Math uses finite doubles; power |exponent|>1024 => numero_invalido, invalid/overflow math => numero_invalido; round precision beyond [-15,15] => numero_invalido. Raw AST validated with named no_desconhecido, existing depth/arity limits plus 2000 node bound. JS context and dict lookup require own data properties (no inherited fields/getter execution). No array/dictionary literal grammar added.
