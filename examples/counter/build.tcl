# Run from the example directory with: xtclsh build.tcl
set source_dir [file dirname [file normalize [info script]]]
set output_dir [file join $source_dir build]
file mkdir $output_dir
cd $output_dir

if {[catch {
    # This project is generated from the sources on every invocation.
    file delete -force counter.xise
    project new counter.xise
    project set family XC9500XL
    project set device xc9572xl
    project set package VQ44
    project set speed -10
    project set "Preferred Language" Verilog
    xfile add [file join $source_dir counter.v]
    xfile add [file join $source_dir counter.ucf]
    project set top counter
    set result [process run "Implement Design" -force rerun_all]
    set status [process get "Implement Design" status]
    project close
    if {!$result || ($status ne "up_to_date" && $status ne "warnings")} {
        error "Implement Design failed with status '$status'"
    }
    if {![file exists counter.jed] || [file size counter.jed] == 0} {
        error "No programming file was generated"
    }
} message]} {
    puts stderr $message
    catch {project close}
    exit 1
}
puts "Built [file join $output_dir counter.jed]"
