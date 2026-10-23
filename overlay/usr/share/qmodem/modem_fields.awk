# Parse Huawei CNUM/HCSQ response lines. Unrelated URCs are ignored.
function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
function csv(s, a,    i,n,c,q,nextc) {
    n=1; q=0; a[n]=""
    for (i=1; i<=length(s); i++) {
        c=substr(s,i,1); nextc=substr(s,i+1,1)
        if (c=="\"") {
            if (q && nextc=="\"") { a[n]=a[n] "\""; i++ }
            else q=!q
        } else if (c=="," && !q) { n++; a[n]="" }
        else a[n]=a[n] c
    }
    return q ? 0 : n
}
mode=="cnum" && /^[ \t]*\+CNUM[ \t]*:/ {
    line=$0; sub(/^[ \t]*\+CNUM[ \t]*:[ \t]*/, "", line)
    if (csv(line, fields)<3) next
    number=trim(fields[2]); kind=trim(fields[3])
    # The first field is a label, never a fallback subscriber number.
    if (number !~ /^\+?[0-9]+$/) next
    digits=number; sub(/^\+/, "", digits)
    if (length(digits)<3 || length(digits)>15) next
    if (kind=="145" && number !~ /^\+/) number="+" number
    print number; exit
}
mode=="lte_sinr" && /^[ \t]*\^HCSQ[ \t]*:/ {
    line=$0; sub(/^[ \t]*\^HCSQ[ \t]*:[ \t]*/, "", line)
    if (csv(line, fields)<5 || trim(fields[1])!="LTE") next
    # LTE order: RSSI, RSRP, SINR, RSRQ. 255/reserved values are unknown.
    value=trim(fields[4])
    if (value !~ /^[0-9]+$/ || value+0>251) next
    printf "%.0f\n", -20 + (value+0>250 ? 250 : value+0)*0.2
    exit
}
